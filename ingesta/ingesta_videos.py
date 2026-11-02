#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ingesta_videos.py - parte determinista de la ingesta de grabaciones.

Dos fases, separadas por una bandeja local (C:\\V\\.ingesta\\bandeja):

1. `procesar`: por cada video nuevo y terminado de C:\\V, de uno en uno y con
   prioridad baja, ejecuta /watch UNA sola vez fuera de OneDrive: transcripcion
   local con Parakeet, frames por cambio de escena y frames dirigidos en los
   instantes en que la transcripcion cita un ticket o algo que se ensena en
   pantalla. Guarda tambien el audio en Opus mono (14 MB/h aprox.), para poder
   diarizar o retranscribir cuando el video ya no exista. Lo deja todo en la
   bandeja con un video.json (inicio y fin en hora local y UTC, para buscar la
   convocatoria de Teams).

   Entre las dos fases, `hojas` y `frames` permiten revisar los frames en la
   bandeja: quitar los que no aportan y sacar del video los que faltan.

2. `publicar`: mueve un elemento de la bandeja a su destino. Decide el destino
   por reglas (enrutado.json, junto a este script): un seguimiento del servicio va a
   SecondB/Control Servicio EMS/reuniones/<fecha>-<EMS|Axapta>/ con los nombres
   de trans-reunion; todo lo demas a Know/<fecha> <titulo>/. El titulo lo da el
   nombre del fichero si lo tiene, si no el asunto de la convocatoria, si no el
   que se le pase. Quien busca la convocatoria (calendario de Outlook) es la
   skill ingesta-v; aqui no hay red ni modelo.

Nunca toca carpetas de reunion que ya existan ni borra videos. Un video cuenta
como ya tratado si algun .md de la bandeja, de Know o de SecondB cita su nombre
de fichero en una linea Source:/Fuente:/Origen:/Grabacion:. Por eso el estado
local se puede perder sin reprocesar nada.

Comandos:
    inventario [--todos]    estado de cada video (pendiente, en-bandeja, publicado, borrable...)
    procesar [--max N]      procesa los pendientes, de uno en uno, el mas antiguo primero
    bandeja [--json]        elementos listos para publicar, con su ventana horaria
    hojas <elemento>        mosaicos numerados de sus frames, para revisarlos
    frames <elemento> [--quitar a.jpg,b.jpg] [--anadir "12:30 motivo"]...
    publicar <elemento> [--asunto S] [--titulo T] [--convocatoria F]
    revisar <elemento> <motivo>   aparta un elemento para decision manual
    pendientes [--json]     publicados que faltan por consolidar (Know) o ingerir (SecondB)
    sugerencia [--corto]    modelo y esfuerzo recomendados para /ingesta-v
    ignorar <video>...      no procesar nunca estos videos
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from datetime import datetime, timezone

# --- configuracion --------------------------------------------------------------

ONEDRIVE = os.path.join(os.path.expanduser("~"), "OneDrive - FORTIA ENERGIA S.L")
KNOW = os.path.join(ONEDRIVE, "Cajon", "Know")
SECONDB = os.path.join(ONEDRIVE, "SecondB", "Control Servicio EMS")
ORIGEN = r"C:\V"
# Trabajo, bandeja, estado y log: disco local, fuera de OneDrive. No en
# %LOCALAPPDATA%, porque el Python de la Microsoft Store virtualiza esa ruta.
LOCAL = os.path.join(ORIGEN, ".ingesta")
WATCH = os.path.join(os.path.expanduser("~"), ".claude", "skills", "watch", "scripts", "watch.py")
ENRUTADO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "enrutado.json")

VIDEO_EXT = {".mp4", ".mkv", ".webm", ".mov", ".avi"}
MIN_BYTES = 1_000_000          # por debajo, grabacion vacia o abortada
ESTABLE_MIN = 10               # minutos sin modificarse para darla por terminada
MAX_INTENTOS = 3               # fallos seguidos antes de dejar de reintentar
LOCK_HORAS = 8                 # un lock mas viejo se considera huerfano

# Frames: deteccion de escena sin tope de modo, deduplicada, con techo duro.
RESOLUCION = 1280
MAX_FRAMES = 300
# Frames dirigidos por la transcripcion.
CUE_HUECO_S = 20               # no hace falta si ya hay un frame a menos de esto
MAX_CUES = 80
SIN_FRAMES_RE = re.compile(r"\s*\bsin frames\b", re.IGNORECASE)
# Audio que sobrevive al video: Opus mono, voz.
AUDIO = "audio.ogg"
AUDIO_KBPS = 32

# Que el portatil siga usable mientras transcribe: los hijos heredan la prioridad.
PRIORIDAD_BAJA = getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)

FECHA_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")
HORA_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2})-(\d{2})-(\d{2})$")
TS_LINE_RE = re.compile(r"^\[(\d{1,2}:\d{2}(?::\d{2})?)\]\s*(.*)$")
FRAME_LINE_RE = re.compile(r"^- `(.+?)` \(t=(\d{1,2}:\d{2}(?::\d{2})?)", re.MULTILINE)
FRAME_T_RE = re.compile(r"\(t=(\d{1,2}:\d{2}(?::\d{2})?)")
DURACION_RE = re.compile(r"\*\*Duration:\*\*.*?\(([\d.]+)s\)")
CUE_RE = re.compile(
    r"\b\d{5}\b"
    r"|\b(ticket|tiquet|peticion|incidencia)\w*"
    r"|\b(pantalla|comparto|compartir|compartiendo)\b"
    r"|\baqui (lo |la |los |las )?(tienes|tenemos|teneis|ves|veis|vemos|esta|estan)\b"
    r"|\b(mira|mirad|fijate|fijaos)\b"
    r"|\bcomo (ves|veis|vemos)\b"
    r"|\b(la tabla|el excel|esta columna|este campo|el error|este error)\b")
NOMBRE_INVALIDO_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Lineas de cabecera que citan el video de origen.
CITA_RE = re.compile(r"(source|fuente|origen|grabaci[oó]n)", re.IGNORECASE)
CABECERA_LINEAS = 40


# --- utilidades -----------------------------------------------------------------

def norm(text: str) -> str:
    """minusculas, sin acentos, separadores unificados y espacios colapsados."""
    t = unicodedata.normalize("NFKD", text)
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = t.replace("\\", "/")
    return re.sub(r"\s+", " ", t).strip()


def seconds(ts: str) -> int:
    total = 0
    for p in ts.split(":"):
        total = total * 60 + int(p)
    return total


def fmt(sec: float) -> str:
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def log(msg: str) -> None:
    os.makedirs(LOCAL, exist_ok=True)
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    print(line, flush=True)
    with open(os.path.join(LOCAL, "ingesta.log"), "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def cargar_estado() -> dict:
    try:
        with open(os.path.join(LOCAL, "estado.json"), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def guardar_estado(estado: dict) -> None:
    os.makedirs(LOCAL, exist_ok=True)
    tmp = os.path.join(LOCAL, "estado.json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(estado, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, os.path.join(LOCAL, "estado.json"))


def bandeja_dir() -> str:
    return os.path.join(LOCAL, "bandeja")


def leer(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def escribir(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


# --- donde esta cada video ------------------------------------------------------

def _cabecera(path: str) -> list[str]:
    lineas = []
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for _ in range(CABECERA_LINEAS):
                line = fh.readline()
                if not line:
                    break
                lineas.append(line)
    except OSError:
        pass
    return lineas


def citas(raices: list[tuple[str, str]]) -> list[tuple[str, str, str]]:
    """(tipo, carpeta, texto normalizado) de las lineas que citan un video.

    Cada raiz es (tipo, ruta) y solo se miran sus carpetas de primer nivel.
    """
    out = []
    for tipo, raiz in raices:
        if not os.path.isdir(raiz):
            continue
        for nombre in os.listdir(raiz):
            carpeta = os.path.join(raiz, nombre)
            if not os.path.isdir(carpeta):
                continue
            trozos = []
            for f in os.listdir(carpeta):
                if f.lower().endswith(".md"):
                    trozos += [norm(x) for x in _cabecera(os.path.join(carpeta, f))
                               if CITA_RE.search(x)]
            if trozos:
                out.append((tipo, carpeta, "\n".join(trozos)))
    return out


def raices(know: str, secondb: str) -> list[tuple[str, str]]:
    return [("bandeja", bandeja_dir()), ("know", know),
            ("secondb", os.path.join(secondb, "reuniones"))]


def consolidada(tipo: str, carpeta: str, secondb: str) -> bool:
    """Know: resumen + meta.json. SecondB: ingesta-<id>.json + pagina en memoria."""
    ficheros = {f.lower() for f in os.listdir(carpeta)}
    if tipo == "know":
        return bool(ficheros & {"summary.md", "resumen.md"}) and "meta.json" in ficheros
    if tipo == "secondb":
        rid = os.path.basename(carpeta)
        return (f"ingesta-{rid}.json".lower() in ficheros and os.path.exists(
            os.path.join(secondb, "memoria", "reuniones", f"{rid}.md")))
    return False


# --- inventario -----------------------------------------------------------------

def nombre_elemento(video: str) -> str:
    stem = re.sub(r"\s+", " ", os.path.splitext(os.path.basename(video))[0]).strip()
    if not FECHA_RE.match(stem):
        fecha = datetime.fromtimestamp(os.path.getmtime(video)).strftime("%Y-%m-%d")
        stem = f"{fecha} {stem}"
    return stem


def clasificar(video: str, cit: list, estado: dict, ahora: float,
               secondb: str) -> tuple[str, str]:
    """(estado, carpeta donde esta, si esta en alguna)."""
    base = os.path.basename(video)
    clave = norm(base)
    if base in estado.get("ignorados", []):
        return "ignorado", ""
    for tipo, carpeta, texto in cit:
        if clave in texto:
            if tipo == "bandeja":
                rev = os.path.basename(carpeta) in estado.get("revisar", {})
                return ("revisar" if rev else "en-bandeja"), carpeta
            return ("borrable" if consolidada(tipo, carpeta, secondb) else "publicado"), carpeta
    if os.path.getsize(video) < MIN_BYTES:
        return "descartado", ""
    if ahora - os.path.getmtime(video) < ESTABLE_MIN * 60:
        return "grabando", ""
    info = estado.get("videos", {}).get(base, {})
    if info.get("sin_audio"):
        return "sin-audio", ""
    if info.get("intentos", 0) >= MAX_INTENTOS:
        return "fallido", ""
    return "pendiente", ""


def videos(origen: str) -> list[str]:
    out = []
    for f in os.listdir(origen):
        p = os.path.join(origen, f)
        if os.path.isfile(p) and os.path.splitext(f)[1].lower() in VIDEO_EXT:
            out.append(p)
    return sorted(out, key=os.path.getmtime)


def inventario(origen: str, know: str, secondb: str) -> list[tuple[str, str, str]]:
    cit = citas(raices(know, secondb))
    estado = cargar_estado()
    ahora = time.time()
    return [(v, *clasificar(v, cit, estado, ahora, secondb)) for v in videos(origen)]


# --- frames dirigidos -----------------------------------------------------------

def lineas_transcripcion(report: str) -> list[tuple[int, str]]:
    """(segundo, texto) de las lineas [MM:SS] del bloque de transcripcion."""
    out, dentro = [], False
    for line in report.splitlines():
        if line.startswith("## Transcript"):
            dentro = True
            continue
        if dentro:
            m = TS_LINE_RE.match(line.strip())
            if m:
                out.append((seconds(m.group(1)), m.group(2)))
    return out


def tiempos_de_frames(report: str) -> list[int]:
    return [seconds(m.group(1)) for m in FRAME_T_RE.finditer(report)]


def elegir_cues(lineas: list[tuple[int, str]], existentes: list[int],
                hueco: int = CUE_HUECO_S, maximo: int = MAX_CUES) -> list[tuple[int, str]]:
    """Instantes que merecen frame y aun no lo tienen a menos de `hueco` s."""
    tomados = list(existentes)
    cues = []
    for t, texto in lineas:
        if not CUE_RE.search(norm(texto)):
            continue
        if any(abs(t - x) < hueco for x in tomados):
            continue
        cues.append((t, texto))
        tomados.append(t)
        if len(cues) >= maximo:
            break
    return cues


def ffmpeg(args: list[str]) -> bool:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args],
                       capture_output=True, creationflags=PRIORIDAD_BAJA)
    return r.returncode == 0


def extraer_frame(video: str, t: int, destino: str) -> bool:
    return ffmpeg(["-ss", str(t), "-i", video, "-frames:v", "1",
                   "-vf", f"scale='min({RESOLUCION},iw)':-2", "-q:v", "3",
                   destino]) and os.path.exists(destino)


def extraer_audio(video: str, destino: str) -> bool:
    return ffmpeg(["-i", video, "-vn", "-ac", "1", "-c:a", "libopus",
                   "-b:a", f"{AUDIO_KBPS}k", "-application", "voip",
                   destino]) and os.path.exists(destino)


def anadir_cues(report: str, cues: list[tuple[int, str, str]],
                titulo: str = "Frames dirigidos por la transcripcion",
                razon: str = "cue") -> str:
    """Inserta una lista de frames justo antes de ## Transcript."""
    if not cues:
        return report
    bloque = [f"### {titulo}", ""]
    for t, path, texto in cues:
        motivo = texto.replace("`", "'")[:80]
        bloque.append(f"- `{path}` (t={fmt(t)}, reason={razon}: {motivo})")
    bloque += ["", ""]
    i = report.find("## Transcript")
    if i < 0:
        return report.rstrip("\n") + "\n\n" + "\n".join(bloque)
    return report[:i] + "\n".join(bloque) + report[i:]


# --- ventana horaria ------------------------------------------------------------

def ventana(video: str, duracion: float) -> dict:
    """Inicio y fin de la grabacion. El nombre de OBS (fecha y hora) manda sobre
    el mtime, que es el final de la grabacion."""
    m = HORA_RE.match(nombre_elemento(video))
    if m:
        inicio = datetime.strptime(" ".join(m.groups()), "%Y-%m-%d %H %M %S").astimezone()
        fin = datetime.fromtimestamp(inicio.timestamp() + duracion).astimezone()
    else:
        fin = datetime.fromtimestamp(os.path.getmtime(video)).astimezone()
        inicio = datetime.fromtimestamp(fin.timestamp() - duracion).astimezone()
    utc = timezone.utc
    return {"inicio_local": inicio.isoformat(timespec="seconds"),
            "fin_local": fin.isoformat(timespec="seconds"),
            "inicio_utc": inicio.astimezone(utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "fin_utc": fin.astimezone(utc).strftime("%Y-%m-%dT%H:%M:%SZ")}


# --- procesar un video a la bandeja ---------------------------------------------

FASES_WATCH = [            # (texto en watch.log, fase que se muestra), la ultima que aparezca
    ("using local file", "preparando"),
    ("extracting scene", "frames por escena"),
    ("extracting keyframes", "frames por escena"),
    ("extracting audio", "extrayendo audio"),
    ("loading parakeet", "cargando Parakeet"),
    ("transcribing", "transcribiendo"),
    ("transcribed", "escribiendo informe"),
]


def fase_de_watch(watch_log: str) -> str:
    try:
        with open(watch_log, encoding="utf-8", errors="replace") as fh:
            texto = fh.read().lower()
    except OSError:
        return "preparando"
    fase, pos = "preparando", -1
    for clave, nombre in FASES_WATCH:
        i = texto.rfind(clave)
        if i > pos:
            fase, pos = nombre, i
    return fase


def duracion_video(video: str) -> float | None:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", video], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


UMBRAL_SILENCIO_DB = -60.0    # pico por debajo de esto: pista muda (OBS sin fuentes de audio)


class SinAudio(RuntimeError):
    """La grabacion no tiene sonido: no es un fallo y no se reintenta."""


def volumen(path: str) -> float | None:
    """Pico de volumen en dB de la pista de audio (volumedetect de ffmpeg)."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-vn",
                        "-af", "volumedetect", "-f", "null", "-"],
                       capture_output=True, text=True, errors="replace",
                       creationflags=PRIORIDAD_BAJA)
    m = re.search(r"max_volume:\s*(-?[\d.]+|-inf) dB", r.stderr)
    if not m:
        return None
    return float("-inf") if m.group(1) == "-inf" else float(m.group(1))


def _sin_avance(fase: str) -> None:
    pass


def procesar_video(video: str, watch: str = WATCH, extractor=extraer_frame,
                   audio=extraer_audio, avance=_sin_avance, volumen=volumen) -> str:
    """Ejecuta watch en local y deja el resultado en la bandeja.

    `avance(fase)` se llama cada 2 s mientras corre watch y al cambiar de fase.
    Devuelve la carpeta de la bandeja. Lanza RuntimeError si falla.
    """
    nombre = nombre_elemento(video)
    # Antes de gastar minutos en watch: una pista muda se descarta en segundos.
    avance("comprobando audio")
    pico = volumen(video)
    if pico is not None and pico <= UMBRAL_SILENCIO_DB:
        raise SinAudio(f"grabacion sin sonido (pico {pico:.0f} dB): nada que transcribir")
    trabajo = os.path.join(LOCAL, "trabajo", nombre)
    if os.path.exists(trabajo):
        shutil.rmtree(trabajo)              # resto de un intento anterior nuestro
    os.makedirs(trabajo)

    sin_frames = bool(SIN_FRAMES_RE.search(nombre))
    cmd = [sys.executable, watch, video, "--out-dir", trabajo, "--whisper", "parakeet",
           "--resolution", str(RESOLUCION)]
    cmd += (["--detail", "transcript"] if sin_frames
            else ["--detail", "token-burner", "--max-frames", str(MAX_FRAMES)])
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    watch_log = os.path.join(trabajo, "watch.log")
    with open(watch_log, "w", encoding="utf-8") as out:
        p = subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT, env=env,
                             creationflags=PRIORIDAD_BAJA)
        while True:
            try:
                p.wait(timeout=2)
                break
            except subprocess.TimeoutExpired:
                avance(fase_de_watch(watch_log))
    report_path = os.path.join(trabajo, "report.md")
    if p.returncode != 0 or not os.path.exists(report_path):
        raise RuntimeError(f"watch devolvio {p.returncode}; ver {trabajo}\\watch.log")

    report = leer(report_path)
    if "**Transcript:** none available" in report:
        # watch lo resume como "Whisper returned no transcript segments" aunque el
        # backend sea Parakeet: distinguir una grabacion muda de un fallo real.
        wav = os.path.join(trabajo, "audio.parakeet.wav")
        pico = volumen(wav if os.path.exists(wav) else video)
        if pico is not None and pico <= UMBRAL_SILENCIO_DB:
            shutil.rmtree(trabajo, ignore_errors=True)
            raise SinAudio(f"grabacion sin sonido (pico {pico:.0f} dB): nada que transcribir")
        raise RuntimeError(f"Parakeet no devolvio transcripcion; ver {watch_log}")
    if "parakeet" not in report.lower():
        raise RuntimeError("la transcripcion no viene de Parakeet; se detiene (audio confidencial)")
    lineas = lineas_transcripcion(report)
    if not lineas:
        raise RuntimeError("report.md sin transcripcion")

    # watch escribe rutas absolutas resueltas a su manera: se toma la que declara.
    elemento = os.path.join(bandeja_dir(), nombre)
    m = re.search(r"Frames live at: `(.+?)[\\/]frames`", report)
    for ruta in {m.group(1) if m else trabajo, trabajo}:
        report = report.replace(ruta, elemento)

    frames_dir = os.path.join(trabajo, "frames")
    if not sin_frames:
        avance("frames dirigidos")
        os.makedirs(frames_dir, exist_ok=True)
        cues = []
        for t, texto in elegir_cues(lineas, tiempos_de_frames(report)):
            nombre_cue = f"cue_{t:05d}.jpg"
            if extractor(video, t, os.path.join(frames_dir, nombre_cue)):
                cues.append((t, os.path.join(elemento, "frames", nombre_cue), texto))
        report = anadir_cues(report, cues)

    avance("audio Opus")
    if not audio(video, os.path.join(trabajo, AUDIO)):
        raise RuntimeError("no se pudo extraer el audio")

    dur = DURACION_RE.search(report)
    info = {"video": video, "elemento": nombre, "sin_frames": sin_frames,
            "duracion_s": float(dur.group(1)) if dur else None,
            "destino_por_nombre": destino_por_nombre(nombre),
            **ventana(video, float(dur.group(1)) if dur else 0.0)}

    # Publicacion en la bandeja: carpeta oculta y renombrado al final.
    parcial = os.path.join(bandeja_dir(), f".{nombre}.parcial")
    if os.path.exists(parcial):
        shutil.rmtree(parcial)
    os.makedirs(parcial)
    escribir(os.path.join(parcial, "report.md"), report)
    with open(os.path.join(parcial, "video.json"), "w", encoding="utf-8") as fh:
        json.dump(info, fh, ensure_ascii=False, indent=1)
    shutil.copy2(os.path.join(trabajo, AUDIO), os.path.join(parcial, AUDIO))
    if os.path.isdir(frames_dir) and os.listdir(frames_dir):
        shutil.copytree(frames_dir, os.path.join(parcial, "frames"))
    if os.path.exists(elemento):
        raise RuntimeError(f"{elemento} ya existe en la bandeja; no se pisa")
    os.rename(parcial, elemento)
    shutil.rmtree(trabajo, ignore_errors=True)
    return elemento


# --- revision de frames en la bandeja -------------------------------------------

HOJA_COLS, HOJA_FILAS, HOJA_ANCHO = 4, 3, 480


def frames_del_report(report: str) -> list[tuple[str, int]]:
    """(nombre de fichero, segundo) de cada frame listado, en orden del informe."""
    return [(os.path.basename(m.group(1)), seconds(m.group(2)))
            for m in FRAME_LINE_RE.finditer(report)]


def hojas(elemento: str) -> list[str]:
    """Mosaicos numerados de los frames, para revisarlos de un vistazo.

    Se escriben en <elemento>/.hojas/, que no se publica. Necesita Pillow.
    """
    from PIL import Image, ImageDraw   # solo aqui: el resto del script es stdlib

    origen = os.path.join(bandeja_dir(), elemento)
    report = leer(os.path.join(origen, "report.md"))
    frames = sorted(frames_del_report(report), key=lambda f: f[1])
    salida = os.path.join(origen, ".hojas")
    if os.path.exists(salida):
        shutil.rmtree(salida)
    os.makedirs(salida)
    por_hoja = HOJA_COLS * HOJA_FILAS
    alto_celda = HOJA_ANCHO * 9 // 16 + 28
    rutas = []
    for n in range(0, len(frames), por_hoja):
        hoja = Image.new("RGB", (HOJA_COLS * HOJA_ANCHO, HOJA_FILAS * alto_celda), "white")
        dibujo = ImageDraw.Draw(hoja)
        for i, (nombre, t) in enumerate(frames[n:n + por_hoja]):
            x, y = (i % HOJA_COLS) * HOJA_ANCHO, (i // HOJA_COLS) * alto_celda
            try:
                with Image.open(os.path.join(origen, "frames", nombre)) as im:
                    im.thumbnail((HOJA_ANCHO - 8, alto_celda - 32))
                    hoja.paste(im, (x + 4, y + 26))
            except OSError:
                pass
            dibujo.text((x + 6, y + 6), f"{nombre}  t={fmt(t)}", fill="black")
        ruta = os.path.join(salida, f"hoja-{n // por_hoja + 1:02d}.jpg")
        hoja.save(ruta, quality=80)
        rutas.append(ruta)
    return rutas


def editar_frames(elemento: str, quitar: list[str], anadir: list[tuple[int, str]],
                  extractor=extraer_frame) -> dict:
    """Quita frames (fichero y linea del informe) y saca otros del video."""
    origen = os.path.join(bandeja_dir(), elemento)
    report_path = os.path.join(origen, "report.md")
    report = leer(report_path)
    frames_dir = os.path.join(origen, "frames")
    quitados = []
    for nombre in quitar:
        nombre = os.path.basename(nombre)
        linea = re.compile(r"^- `[^`]*[\\/]" + re.escape(nombre) + r"` \(t=.*\n?", re.MULTILINE)
        if not linea.search(report):
            raise RuntimeError(f"{nombre} no esta en el informe")
        report = linea.sub("", report)
        try:
            os.remove(os.path.join(frames_dir, nombre))
        except OSError:
            pass
        quitados.append(nombre)
    nuevos = []
    if anadir:
        with open(os.path.join(origen, "video.json"), encoding="utf-8") as fh:
            video = json.load(fh)["video"]
        if not os.path.exists(video):
            raise RuntimeError(f"el video ya no existe: {video}")
        os.makedirs(frames_dir, exist_ok=True)
        for t, motivo in anadir:
            nombre = f"extra_{t:05d}.jpg"
            if not extractor(video, t, os.path.join(frames_dir, nombre)):
                raise RuntimeError(f"no se pudo extraer el frame de {fmt(t)}")
            nuevos.append((t, os.path.join(frames_dir, nombre), motivo))
        report = anadir_cues(report, nuevos, "Frames anadidos en la revision", "manual")
    escribir(report_path, report)
    return {"quitados": len(quitados), "anadidos": len(nuevos),
            "quedan": len(frames_del_report(report))}


# --- enrutado y publicacion -----------------------------------------------------

def cargar_enrutado(path: str = ENRUTADO) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def titulo_de_fichero(nombre: str) -> str:
    """Lo que el nombre dice ademas de la fecha; vacio si solo es fecha y hora."""
    if HORA_RE.match(nombre):
        return ""
    resto = FECHA_RE.sub("", nombre)
    return SIN_FRAMES_RE.sub("", resto).strip(" -_")


def destino_por_nombre(nombre: str, reglas: dict | None = None) -> str | None:
    reglas = reglas if reglas is not None else cargar_enrutado()
    for patron, sistema in reglas.get("secondb_por_nombre", {}).items():
        if re.search(patron, norm(nombre)):
            return sistema
    return None


def enrutar(nombre: str, asunto: str | None, reglas: dict) -> tuple[str, str | None]:
    """('secondb', sistema) o ('know', None). El nombre del fichero manda."""
    sistema = destino_por_nombre(nombre, reglas)
    if sistema is None and asunto:
        for patron, s in reglas.get("secondb_por_asunto", {}).items():
            if norm(patron) == norm(asunto):
                sistema = s
                break
    return ("secondb", sistema) if sistema else ("know", None)


def limpiar_nombre(texto: str, maximo: int = 100) -> str:
    t = re.sub(r"\s+", " ", NOMBRE_INVALIDO_RE.sub(" ", texto)).strip()
    return t[:maximo].rstrip(" .")


def nombre_t(t: str, usados: set[str]) -> str:
    """t-MMSS.jpg (o t-HHMMSS.jpg), sin repetir dentro de la reunion."""
    base = "t-" + t.replace(":", "")
    nombre, n = f"{base}.jpg", 2
    while nombre in usados:
        nombre, n = f"{base}-{n}.jpg", n + 1
    usados.add(nombre)
    return nombre


def publicar(elemento: str, asunto: str | None = None, titulo: str | None = None,
             convocatoria: dict | None = None, know: str = KNOW,
             secondb: str = SECONDB, reglas: dict | None = None) -> dict:
    """Mueve un elemento de la bandeja a Know o a SecondB. Devuelve el destino."""
    reglas = reglas if reglas is not None else cargar_enrutado()
    origen = os.path.join(bandeja_dir(), elemento)
    if not os.path.isdir(origen):
        raise RuntimeError(f"no esta en la bandeja: {elemento}")
    if convocatoria and not asunto:
        asunto = convocatoria.get("asunto")
    fecha = elemento[:10]
    destino, sistema = enrutar(elemento, asunto, reglas)
    report = leer(os.path.join(origen, "report.md"))

    if destino == "secondb":
        rid = f"{fecha}-{sistema}"
        raiz = os.path.join(secondb, "reuniones")
        final = os.path.join(raiz, rid)
        if os.path.exists(final):
            raise RuntimeError(f"ya existe {final}: dos seguimientos de {sistema} el mismo dia; revisar")
        nombre_report, nombre_frames = f"transcripcion-{rid}.md", f"frames-{rid}"
    else:
        titulo = titulo_de_fichero(elemento) or (asunto or "").strip() or (titulo or "").strip()
        if not titulo:
            raise RuntimeError("sin titulo: ni el fichero ni la convocatoria lo dan; pasa --titulo")
        raiz = know
        base = limpiar_nombre(f"{fecha} {titulo}")
        final, n = os.path.join(raiz, base), 2
        while os.path.exists(final):
            final, n = os.path.join(raiz, f"{base} ({n})"), n + 1
        nombre_report, nombre_frames = "report.md", "frames"

    parcial = os.path.join(raiz, f".{os.path.basename(final)}.parcial")
    if os.path.exists(parcial):
        shutil.rmtree(parcial)
    os.makedirs(parcial)
    frames_src = os.path.join(origen, "frames")
    if os.path.isdir(frames_src):
        os.makedirs(os.path.join(parcial, nombre_frames))
        usados: set[str] = set()
        renombres = {}
        for m in FRAME_LINE_RE.finditer(report):
            viejo = os.path.basename(m.group(1))
            if viejo in renombres or not os.path.exists(os.path.join(frames_src, viejo)):
                continue
            renombres[viejo] = nombre_t(m.group(2), usados) if destino == "secondb" else viejo
        for f in os.listdir(frames_src):
            nuevo = renombres.get(f, f)
            shutil.copy2(os.path.join(frames_src, f), os.path.join(parcial, nombre_frames, nuevo))
        for viejo, nuevo in renombres.items():
            report = report.replace(os.path.join(origen, "frames", viejo),
                                    os.path.join(final, nombre_frames, nuevo))
        report = report.replace(os.path.join(origen, "frames"), os.path.join(final, nombre_frames))
    report = report.replace(origen, final)
    escribir(os.path.join(parcial, nombre_report), report)
    shutil.copy2(os.path.join(origen, AUDIO), os.path.join(parcial, AUDIO))
    if convocatoria:
        with open(os.path.join(parcial, "convocatoria.json"), "w", encoding="utf-8") as fh:
            json.dump(convocatoria, fh, ensure_ascii=False, indent=1)
    os.rename(parcial, final)
    shutil.rmtree(origen)
    estado = cargar_estado()
    if estado.get("revisar", {}).pop(elemento, None) is not None:
        guardar_estado(estado)
    return {"destino": destino, "sistema": sistema, "carpeta": final}


# --- lock -----------------------------------------------------------------------

def tomar_lock() -> bool:
    os.makedirs(LOCAL, exist_ok=True)
    lock = os.path.join(LOCAL, "ingesta.lock")
    if os.path.exists(lock) and time.time() - os.path.getmtime(lock) > LOCK_HORAS * 3600:
        os.remove(lock)
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    return True


def soltar_lock() -> None:
    try:
        os.remove(os.path.join(LOCAL, "ingesta.lock"))
    except OSError:
        pass


# --- comandos -------------------------------------------------------------------

def cmd_inventario(args) -> int:
    filas = inventario(args.origen, args.know, args.secondb)
    estado = cargar_estado()
    cuenta: dict[str, int] = {}
    for v, est, carpeta in filas:
        cuenta[est] = cuenta.get(est, 0) + 1
        if args.todos or est not in ("publicado", "borrable"):
            extra = ""
            if est in ("fallido", "sin-audio"):
                extra = " - " + estado["videos"][os.path.basename(v)].get("error", "")
            elif est == "revisar":
                extra = " - " + estado["revisar"].get(os.path.basename(carpeta), "")
            elif carpeta:
                extra = f" -> {carpeta}"
            print(f"{est:<11} {os.path.basename(v)}{extra}")
    print("\n" + ", ".join(f"{k}: {n}" for k, n in sorted(cuenta.items())))
    if cuenta.get("borrable"):
        print("borrable = ya consolidado en su cerebro; el video se puede borrar a mano "
              "(inventario --todos los lista)")
    if estado.get("ultima_ok"):
        print(f"ultimo video procesado: {estado['ultima_ok']}")
    return 0


def limpiar_trabajo(origen: str, estado: dict) -> list[str]:
    """Borra carpetas de trabajo que ya no sirven para diagnosticar nada.

    Se conserva solo la de un video que sigue en el origen y ha fallado (su
    watch.log explica el fallo). Las de videos borrados o mudos se van.
    """
    raiz = os.path.join(LOCAL, "trabajo")
    vivos = {}
    for v in videos(origen) if os.path.isdir(origen) else []:
        vivos[nombre_elemento(v)] = os.path.basename(v)
    borradas = []
    for nombre in os.listdir(raiz) if os.path.isdir(raiz) else []:
        base = vivos.get(nombre)
        info = estado.get("videos", {}).get(base, {}) if base else {}
        if base and info.get("intentos") and not info.get("sin_audio"):
            continue
        shutil.rmtree(os.path.join(raiz, nombre), ignore_errors=True)
        borradas.append(nombre)
    return borradas


VELOCIDAD_INICIAL = 0.16      # s de proceso por s de video (Parakeet int8 en la CPU del portatil)


def duracion_humana(seg: float) -> str:
    m = int(seg // 60)
    return f"{m // 60} h {m % 60:02d} min" if m >= 60 else f"{max(m, 1)} min"


class Avance:
    """Linea de avance en consola, reescrita en el sitio.

    El porcentaje es una estimacion: duracion del video x velocidad aprendida
    de los anteriores. Se queda en 99 % hasta que el video termina de verdad.
    Fuera de una consola (log, tests) no escribe nada.
    """

    def __init__(self, duraciones: list, velocidad: float, salida=None):
        self.dur = duraciones
        self.vel = velocidad
        self.out = salida or sys.stdout
        self.activo = self.out.isatty()
        self.total = sum(d or 0 for d in duraciones)
        self.hecho = 0.0
        self.i, self.t0, self.ancho = 0, time.time(), 0

    def empezar(self, i: int) -> None:
        self.i, self.t0 = i, time.time()

    def linea(self, fase: str, transcurrido: float) -> str:
        d = self.dur[self.i - 1]
        cab = f"  [{self.i}/{len(self.dur)}]"
        if not d:
            return f"{cab} {fase} · {fmt(transcurrido)}"
        est = d * self.vel
        pct = min(99, int(transcurrido / est * 100)) if est else 0
        barra = "[" + "#" * (pct // 5) + "-" * (20 - pct // 5) + "]"
        partes = [f"{barra} {pct:2d}%", fase, f"{fmt(transcurrido)} de ~{fmt(est)}"]
        if self.total and len(self.dur) > 1:
            hecho = self.hecho + min(d * 0.99, transcurrido / self.vel)
            resta = max(0.0, (self.total - hecho) * self.vel)
            partes.append(f"total {int(hecho / self.total * 100)}%, quedan ~{duracion_humana(resta)}")
        return f"{cab} " + " · ".join(partes)

    def __call__(self, fase: str) -> None:
        if not self.activo:
            return
        texto = self.linea(fase, time.time() - self.t0)
        self.out.write("\r" + texto.ljust(self.ancho))
        self.out.flush()
        self.ancho = len(texto)

    def terminar(self) -> None:
        self.hecho += self.dur[self.i - 1] or 0
        if self.activo and self.ancho:
            self.out.write("\r" + " " * self.ancho + "\r")
            self.out.flush()
            self.ancho = 0


def cmd_procesar(args) -> int:
    if not tomar_lock():
        print("otra ingesta en curso; se sale")
        return 0
    try:
        for nombre in limpiar_trabajo(args.origen, cargar_estado()):
            log(f"limpieza  trabajo\\{nombre}")
        filas = inventario(args.origen, args.know, args.secondb)
        cola = [v for v, est, _ in filas if est == "pendiente"
                and (not args.desde or nombre_elemento(v)[:10] >= args.desde)]
        if args.solo:
            cola = [v for v in cola if os.path.basename(v) == args.solo]
        if args.max:
            cola = cola[:args.max]
        if not cola:
            print("nada pendiente")
            return 0
        duraciones = [duracion_video(v) for v in cola]
        av = Avance(duraciones, cargar_estado().get("velocidad", VELOCIDAD_INICIAL))
        if av.total:
            print(f"{len(cola)} video(s), {duracion_humana(av.total)} de grabacion, "
                  f"~{duracion_humana(av.total * av.vel)} estimados", flush=True)
        errores = 0
        for i, v in enumerate(cola, 1):
            base = os.path.basename(v)
            estado = cargar_estado()
            info = estado.setdefault("videos", {}).setdefault(base, {})
            log(f"[{i}/{len(cola)}] inicio  {base}")
            t0 = time.time()
            av.empezar(i)
            try:
                elemento = procesar_video(v, args.watch, avance=av)
            except SinAudio as e:
                av.terminar()
                info.update({"sin_audio": True, "error": str(e),
                             "fecha": datetime.now().isoformat(timespec="seconds")})
                guardar_estado(estado)
                log(f"[{i}/{len(cola)}] SIN AUDIO {base}: {e}")
                continue
            except Exception as e:  # noqa: BLE001 - se registra y se sigue con el siguiente
                av.terminar()
                errores += 1
                info["intentos"] = info.get("intentos", 0) + 1
                info["error"] = str(e)[:300]
                info["fecha"] = datetime.now().isoformat(timespec="seconds")
                guardar_estado(estado)
                log(f"[{i}/{len(cola)}] ERROR   {base}: {e}")
                continue
            av.terminar()
            segundos = time.time() - t0
            info.clear()
            info.update({"elemento": os.path.basename(elemento),
                         "fecha": datetime.now().isoformat(timespec="seconds"),
                         "minutos": round(segundos / 60, 1)})
            estado["ultima_ok"] = info["fecha"]
            if duraciones[i - 1]:       # aprende la velocidad para las estimaciones
                medida = segundos / duraciones[i - 1]
                av.vel = round(0.7 * estado.get("velocidad", medida) + 0.3 * medida, 4)
                estado["velocidad"] = av.vel
            guardar_estado(estado)
            log(f"[{i}/{len(cola)}] ok      {base} -> bandeja ({info['minutos']} min)")
        return 1 if errores else 0
    finally:
        soltar_lock()


def elementos_bandeja() -> list[dict]:
    estado = cargar_estado()
    out = []
    raiz = bandeja_dir()
    for nombre in sorted(os.listdir(raiz)) if os.path.isdir(raiz) else []:
        p = os.path.join(raiz, nombre, "video.json")
        if nombre.startswith(".") or not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as fh:
            info = json.load(fh)
        info["titulo_de_fichero"] = titulo_de_fichero(nombre)
        info["revisar"] = estado.get("revisar", {}).get(nombre)
        out.append(info)
    return out


def por_consolidar(know: str, secondb: str) -> list[dict]:
    """Publicados que faltan por consolidar (Know) o por ingerir (SecondB)."""
    out = []
    for nombre in sorted(os.listdir(know)):
        carpeta = os.path.join(know, nombre)
        if nombre.startswith((".", "_")) or not os.path.isdir(carpeta):
            continue
        ficheros = {f.lower() for f in os.listdir(carpeta)}
        if "report.md" in ficheros and not ficheros & {"summary.md", "resumen.md"}:
            out.append({"destino": "know", "carpeta": carpeta})
    reuniones = os.path.join(secondb, "reuniones")
    for rid in sorted(os.listdir(reuniones)) if os.path.isdir(reuniones) else []:
        carpeta = os.path.join(reuniones, rid)
        if (not rid.startswith(".") and os.path.isdir(carpeta)
                and os.path.exists(os.path.join(carpeta, f"transcripcion-{rid}.md"))
                and not os.path.exists(os.path.join(carpeta, f"ingesta-{rid}.json"))):
            out.append({"destino": "secondb", "carpeta": carpeta})
    return out


def sugerir(bandeja: list[dict], pendientes: list[dict]) -> dict:
    """Modelo y esfuerzo para la sesion de /ingesta-v. Sin modelo: reglas fijas.

    - Algun seguimiento del servicio (SecondB): Opus, esfuerzo alto. trans-reunion
      coteja tickets contra Redmine, decide si un tema o una persona es la misma
      que en reuniones anteriores y propone el desenlace de compromisos: errores
      ahi contaminan la memoria y no se detectan despues.
    - Solo Know: Sonnet, esfuerzo alto. Resumen, metadatos, convocatoria y
      revision de frames piden cuidado, pero no ese cruce entre reuniones.
    Nunca xhigh ni max: no aportan a esta tarea y multiplican el razonamiento.
    """
    activos = [b for b in bandeja if not b.get("revisar")]
    secondb = ([b["elemento"] for b in activos if b.get("destino_por_nombre")]
               + [os.path.basename(p["carpeta"]) for p in pendientes if p["destino"] == "secondb"])
    dudosos = [b["elemento"] for b in activos
               if not b.get("destino_por_nombre") and not b.get("titulo_de_fichero")]
    n = len(activos) + len(pendientes)
    if not n:
        return {"modelo": "ninguno", "esfuerzo": "-", "elementos": 0,
                "motivo": "nada en la bandeja ni por consolidar: no hace falta abrir Claude"}
    if secondb:
        return {"modelo": "opus", "esfuerzo": "high", "elementos": n, "secondb": secondb,
                "dudosos": dudosos,
                "motivo": f"{len(secondb)} seguimiento(s) del servicio: trans-reunion coteja "
                          "tickets, compromisos e identidades entre reuniones"}
    return {"modelo": "sonnet", "esfuerzo": "high", "elementos": n, "secondb": [],
            "dudosos": dudosos,
            "motivo": "solo reuniones para Know: resumen, metadatos y revision de frames"}


def cmd_sugerencia(args) -> int:
    s = sugerir(elementos_bandeja(), por_consolidar(args.know, args.secondb))
    if args.corto:
        print(f"{s['modelo']} {s['esfuerzo']}")
        return 0
    if s["modelo"] == "ninguno":
        print(s["motivo"])
        return 0
    print(f"Sugerencia: {s['modelo'].capitalize()}, esfuerzo {s['esfuerzo']} "
          f"({s['elementos']} elemento(s)) - {s['motivo']}.")
    if s["dudosos"] and s["modelo"] != "opus":
        print(f"  {len(s['dudosos'])} sin titulo en el nombre: si la convocatoria resulta ser "
              "un seguimiento, con S lo deja la pasada de Sonnet para la de Opus.")
    return 0


def cmd_bandeja(args) -> int:
    out = elementos_bandeja()
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
    else:
        for i in out:
            marca = f"  [revisar: {i['revisar']}]" if i["revisar"] else ""
            ruta = i["destino_por_nombre"] or "?"
            print(f"{i['elemento']}  {i['inicio_local'][11:16]}-{i['fin_local'][11:16]}"
                  f"  SecondB:{ruta}{marca}")
        print(f"\n{len(out)} en la bandeja" if out else "bandeja vacia")
    return 0


def cmd_publicar(args) -> int:
    conv = None
    if args.convocatoria:
        with open(args.convocatoria, encoding="utf-8") as fh:
            conv = json.load(fh)
    res = publicar(args.elemento, args.asunto, args.titulo, conv, args.know,
                   args.secondb)
    log(f"publicado {args.elemento} -> {res['carpeta']}")
    print(json.dumps(res, ensure_ascii=False))
    return 0


def cmd_hojas(args) -> int:
    for ruta in hojas(args.elemento):
        print(ruta)
    return 0


def cmd_frames(args) -> int:
    anadir = []
    for a in args.anadir or []:
        t, _, motivo = a.strip().partition(" ")
        anadir.append((seconds(t), motivo.strip() or "revision"))
    quitar = [q for grupo in args.quitar or [] for q in re.split(r"[,\s]+", grupo) if q]
    res = editar_frames(args.elemento, quitar, anadir)
    log(f"frames    {args.elemento}: -{res['quitados']} +{res['anadidos']} = {res['quedan']}")
    print(json.dumps(res))
    return 0


def cmd_revisar(args) -> int:
    if not os.path.isdir(os.path.join(bandeja_dir(), args.elemento)):
        print(f"no esta en la bandeja: {args.elemento}")
        return 1
    estado = cargar_estado()
    estado.setdefault("revisar", {})[args.elemento] = args.motivo
    guardar_estado(estado)
    log(f"revisar   {args.elemento}: {args.motivo}")
    return 0


def cmd_pendientes(args) -> int:
    out = por_consolidar(args.know, args.secondb)
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
    else:
        for o in out:
            print(f"{o['destino']:<8} {o['carpeta']}")
        if not out:
            print("nada por consolidar")
    return 0


def cmd_ignorar(args) -> int:
    estado = cargar_estado()
    ign = estado.setdefault("ignorados", [])
    for v in args.videos:
        base = os.path.basename(v)
        if base not in ign:
            ign.append(base)
    guardar_estado(estado)
    print(f"ignorados: {len(ign)}")
    return 0


def main(argv=None) -> int:
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--origen", default=ORIGEN)
    ap.add_argument("--know", default=KNOW)
    ap.add_argument("--secondb", default=SECONDB)
    ap.add_argument("--watch", default=WATCH, help="ruta de watch.py")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("inventario")
    p.add_argument("--todos", action="store_true", help="incluye publicados y borrables")
    p.set_defaults(fn=cmd_inventario)

    p = sub.add_parser("procesar")
    p.add_argument("--max", type=int, default=0, help="como mucho N videos (defecto: todos)")
    p.add_argument("--desde", help="solo videos con fecha >= YYYY-MM-DD")
    p.add_argument("--solo", help="nombre exacto de un video")
    p.set_defaults(fn=cmd_procesar)

    p = sub.add_parser("bandeja")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_bandeja)

    p = sub.add_parser("publicar")
    p.add_argument("elemento", help="nombre de la carpeta en la bandeja")
    p.add_argument("--asunto", help="asunto de la convocatoria de Teams")
    p.add_argument("--titulo", help="titulo si ni el fichero ni la convocatoria lo dan")
    p.add_argument("--convocatoria", help="JSON con asunto, inicio, fin, organizador, invitados")
    p.set_defaults(fn=cmd_publicar)

    p = sub.add_parser("hojas", help="mosaicos numerados de los frames de un elemento")
    p.add_argument("elemento")
    p.set_defaults(fn=cmd_hojas)

    p = sub.add_parser("frames", help="quita frames y saca otros del video")
    p.add_argument("elemento")
    p.add_argument("--quitar", action="append", help="frame_0003.jpg,frame_0007.jpg")
    p.add_argument("--anadir", action="append", help='"12:30 motivo" (repetible)')
    p.set_defaults(fn=cmd_frames)

    p = sub.add_parser("revisar")
    p.add_argument("elemento")
    p.add_argument("motivo")
    p.set_defaults(fn=cmd_revisar)

    p = sub.add_parser("pendientes")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_pendientes)

    p = sub.add_parser("sugerencia", help="modelo y esfuerzo para /ingesta-v")
    p.add_argument("--corto", action="store_true", help='solo "<modelo> <esfuerzo>"')
    p.set_defaults(fn=cmd_sugerencia)

    p = sub.add_parser("ignorar")
    p.add_argument("videos", nargs="+")
    p.set_defaults(fn=cmd_ignorar)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
