#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""salud.py - comprobacion de salud de la ingesta y de los tres segundos cerebros.

Un cerebro que deja de alimentarse sin que nadie lo note no sirve. Esto mira, sin
llamar a ningun modelo y sin escribir en los cerebros:

  videos         C:\\V: pendientes viejos, fallidos, bandeja sin publicar, mudos y
                 los que ya se pueden borrar
  reuniones      Know y SecondB: publicadas sin consolidar desde hace dias
  know           kb.py status: errores de sync, metas invalidos o desactualizados
  second-claude  ultima ingesta registrada en log.md, sesiones paradas en el
                 staging y pendientes de integrar que no bajan
  wiki           enlaces rotos del wiki de Second Claude (tambien a Know y SecondB)
  indice         el indice unico de cerebro.py se abre y tiene fichas

De las sesiones del staging nunca se muestra el titulo: puede ser personal.

    python salud/salud.py [--dias 2] [--json]

Codigo de salida 1 si hay algun aviso.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import tomllib
from datetime import datetime
from urllib.parse import unquote

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, os.path.join(RAIZ, "ingesta"))
sys.path.insert(0, os.path.join(RAIZ, "cerebro"))
import cerebro as cb  # noqa: E402
import ingesta_videos as iv  # noqa: E402

KNOW = iv.KNOW
SECONDB = iv.SECONDB
SECOND_CLAUDE = cb.SECOND_CLAUDE
ORIGEN = iv.ORIGEN

DIAS = 2                      # margen antes de avisar de algo parado
MAX_LISTA = 5                 # nombres que se muestran por aviso
LOG_INGESTA_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}) — ingesta", re.MULTILINE)
ENLACE_RE = re.compile(r"\]\((<[^>]+>|[^)\s]+)\)")
CODIGO_RE = re.compile(r"```.*?```|`[^`\n]*`", re.DOTALL)   # los ejemplos en codigo no son enlaces


def aviso(area: str, texto: str) -> dict:
    return {"nivel": "aviso", "area": area, "texto": texto}


def info(area: str, texto: str) -> dict:
    return {"nivel": "info", "area": area, "texto": texto}


def lista(nombres: list[str]) -> str:
    extra = f" y {len(nombres) - MAX_LISTA} mas" if len(nombres) > MAX_LISTA else ""
    return ", ".join(nombres[:MAX_LISTA]) + extra


def viejo(path: str, ahora: float, dias: float) -> bool:
    return ahora - os.path.getmtime(path) > dias * 86400


# --- videos y reuniones por consolidar ------------------------------------------

def revisar_videos(origen: str, know: str, secondb: str, ahora: float, dias: float) -> list[dict]:
    if not os.path.isdir(origen):
        return [info("videos", f"no existe {origen}")]
    inv = iv.inventario(origen, know, secondb)
    por = {}
    for video, estado, carpeta in inv:
        por.setdefault(estado, []).append((video, carpeta))
    out = []
    viejos = [os.path.basename(v) for v, _ in por.get("pendiente", []) if viejo(v, ahora, dias)]
    if viejos:
        out.append(aviso("videos", f"{len(viejos)} sin procesar desde hace mas de {dias} dias "
                                   f"(lanza LauncherV): {lista(viejos)}"))
    if por.get("fallido"):
        out.append(aviso("videos", f"{len(por['fallido'])} fallidos tras {iv.MAX_INTENTOS} intentos "
                                   f"(motivo en 'inventario'): "
                                   f"{lista([os.path.basename(v) for v, _ in por['fallido']])}"))
    parados = [os.path.basename(c) for est in ("en-bandeja", "revisar") for _, c in por.get(est, [])
               if viejo(c, ahora, dias)]
    if parados:
        out.append(aviso("videos", f"{len(parados)} en la bandeja sin publicar desde hace mas de "
                                   f"{dias} dias (skill ingesta-v): {lista(parados)}"))
    if por.get("sin-audio"):
        out.append(info("videos", f"{len(por['sin-audio'])} mudos (pista de audio en silencio): "
                                  f"borralos o marcalos con 'ignorar'"))
    if por.get("borrable"):
        gb = sum(os.path.getsize(v) for v, _ in por["borrable"]) / 1e9
        out.append(info("videos", f"{len(por['borrable'])} ya consolidados se pueden borrar "
                                  f"({gb:.1f} GB)"))
    return out


def revisar_reuniones(know: str, secondb: str, ahora: float, dias: float) -> list[dict]:
    viejas = [p for p in iv.por_consolidar(know, secondb) if viejo(p["carpeta"], ahora, dias)]
    out = []
    for destino, skill in (("know", "consolida-reuniones"), ("secondb", "trans-reunion")):
        nombres = [os.path.basename(p["carpeta"]) for p in viejas if p["destino"] == destino]
        if nombres:
            out.append(aviso("reuniones", f"{len(nombres)} publicadas en {destino} sin consolidar "
                                          f"desde hace mas de {dias} dias ({skill}): {lista(nombres)}"))
    return out


# --- Know -----------------------------------------------------------------------

def avisos_know(status: dict) -> list[dict]:
    out = []
    sync = status.get("sync", {})
    if not sync.get("ok", True) or sync.get("errores"):
        out.append(aviso("know", f"la ultima sync termino con errores: "
                                 f"{lista([e['path'] for e in sync.get('errores', [])])}"))
    textos = {"sin-resumen": "sin resumen", "meta-invalido": "con meta.json invalido",
              "meta-desactualizado": "con meta.json desactualizado",
              "errores-lectura": "con errores de lectura"}
    for flag, texto in textos.items():
        rutas = status.get("flags", {}).get(flag, [])
        if rutas:
            out.append(aviso("know", f"{len(rutas)} reuniones {texto}: {lista(rutas)}"))
    return out


def revisar_know(know: str) -> list[dict]:
    kb = os.path.join(know, "_kb", "kb.py")
    if not os.path.exists(kb):
        return [aviso("know", f"no existe {kb}")]
    r = subprocess.run([sys.executable, kb, "status", "--json"], cwd=know,
                       capture_output=True, text=True, encoding="utf-8")
    try:
        return avisos_know(json.loads(r.stdout))
    except ValueError:
        return [aviso("know", f"kb.py status no respondio: {(r.stderr or r.stdout).strip()[:200]}")]


# --- Second Claude --------------------------------------------------------------

def staging_de(base: str) -> str:
    with open(os.path.join(base, "config.toml"), "rb") as fh:
        return os.path.expandvars(tomllib.load(fh)["salida"]["staging"])


def ultima_ingesta(log_md: str) -> datetime | None:
    fechas = [datetime.strptime(f"{d} {h}", "%Y-%m-%d %H:%M")
              for d, h in LOG_INGESTA_RE.findall(iv.leer(log_md))]
    return max(fechas) if fechas else None


def revisar_second_claude(base: str, staging: str, ahora: float, dias: float) -> list[dict]:
    out = []
    log_md = os.path.join(base, "log.md")
    ultima = ultima_ingesta(log_md) if os.path.exists(log_md) else None
    if ultima is None:
        out.append(aviso("second-claude", "log.md no tiene ninguna entrada de ingesta"))
    elif ahora - ultima.timestamp() > dias * 86400:
        out.append(aviso("second-claude", f"la ingesta diaria no ha dejado registro desde "
                                          f"{ultima:%Y-%m-%d %H:%M} (tarea second-claude-ingesta)"))
    try:
        with open(os.path.join(staging, "por_clasificar.json"), encoding="utf-8") as fh:
            cola = json.load(fh)
    except (OSError, ValueError):
        cola = []
    paradas = sorted({e["sesion"][:8] for e in cola
                      if os.path.exists(p := os.path.join(staging, "sesiones", e["nombre"]))
                      and viejo(p, ahora, dias)})
    if paradas:
        out.append(aviso("second-claude", f"{len(paradas)} sesiones paradas en el staging desde hace "
                                          f"mas de {dias} dias (por secretos o sin clasificar; ver "
                                          f"log.md): {lista(paradas)}"))
    pend = os.path.join(base, "estado", "pendientes.json")
    if os.path.exists(pend):
        with open(pend, encoding="utf-8") as fh:
            n = len(json.load(fh))
        if n and viejo(pend, ahora, dias):
            out.append(aviso("second-claude", f"{n} resumenes aceptados sin integrar en el wiki desde "
                                              f"hace mas de {dias} dias"))
    return out


def enlaces_rotos(base: str) -> list[tuple[str, str]]:
    """(pagina, destino) de los enlaces relativos del wiki e index.md que no existen."""
    paginas = [os.path.join(base, "index.md")]
    wiki = os.path.join(base, "wiki")
    for raiz, _, ficheros in os.walk(wiki):
        paginas += [os.path.join(raiz, f) for f in ficheros if f.endswith(".md")]
    rotos = []
    for pagina in paginas:
        if not os.path.exists(pagina):
            continue
        for destino in ENLACE_RE.findall(CODIGO_RE.sub("", iv.leer(pagina))):
            destino = destino.strip("<>")
            if re.match(r"^[a-z][a-z0-9+.-]*:", destino, re.IGNORECASE) or destino.startswith("#"):
                continue
            ruta = unquote(destino.split("#", 1)[0])
            if ruta and not os.path.exists(os.path.normpath(os.path.join(os.path.dirname(pagina), ruta))):
                rotos.append((os.path.relpath(pagina, base), destino))
    return rotos


def revisar_wiki(base: str) -> list[dict]:
    rotos = enlaces_rotos(base)
    if not rotos:
        return []
    paginas = sorted({p for p, _ in rotos})
    return [aviso("wiki", f"{len(rotos)} enlaces rotos en {len(paginas)} paginas: "
                          f"{lista([f'{p} -> {d}' for p, d in rotos])}")]


# --- indice unico ---------------------------------------------------------------

def revisar_indice() -> list[dict]:
    try:
        con = cb.abrir()
        n = con.execute("SELECT count(*) FROM fichas").fetchone()[0]
        a = con.execute("SELECT count(*) FROM atomos").fetchone()[0]
        con.close()
    except Exception as e:  # noqa: BLE001 - cualquier fallo del indice es un aviso
        return [aviso("indice", f"no se pudo abrir el indice unico: {e}")]
    if not n:
        return [aviso("indice", "el indice unico no tiene fichas")]
    return [info("indice", f"{n} fichas y {a} atomos")]


# --- informe --------------------------------------------------------------------

def comprobar(dias: float = DIAS, ahora: float | None = None) -> list[dict]:
    ahora = time.time() if ahora is None else ahora
    out = []
    for nombre, fn in (
            ("videos", lambda: revisar_videos(ORIGEN, KNOW, SECONDB, ahora, dias)),
            ("reuniones", lambda: revisar_reuniones(KNOW, SECONDB, ahora, dias)),
            ("know", lambda: revisar_know(KNOW)),
            ("second-claude", lambda: revisar_second_claude(
                SECOND_CLAUDE, staging_de(SECOND_CLAUDE), ahora, dias)),
            ("wiki", lambda: revisar_wiki(SECOND_CLAUDE)),
            ("indice", revisar_indice)):
        try:
            out += fn()
        except Exception as e:  # noqa: BLE001 - una comprobacion rota no tapa las demas
            out.append(aviso(nombre, f"la comprobacion fallo: {type(e).__name__}: {e}"))
    return out


def main(argv=None) -> int:
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dias", type=float, default=DIAS, help="margen antes de avisar (defecto 2)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    res = comprobar(args.dias)
    avisos = [r for r in res if r["nivel"] == "aviso"]
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        for r in avisos + [r for r in res if r["nivel"] == "info"]:
            print(f"{'AVISO' if r['nivel'] == 'aviso' else 'info '}  {r['area']:<14} {r['texto']}")
        print(f"{len(avisos)} aviso(s)" if avisos else "Todo en orden")
    return 1 if avisos else 0


if __name__ == "__main__":
    sys.exit(main())
