#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cerebro.py - indice unico de los tres segundos cerebros.

Lee, sin modificarlos, los tres archivos de conocimiento y los indexa juntos:

  Know          OneDrive/Cajon/Know/<reunion>/          summary.md + meta.json
  SecondB       OneDrive/SecondB/Control Servicio EMS/memoria/
                  reuniones/*.md, tickets/*.md, historial_tickets.csv,
                  acuerdos.csv, temas.csv
  Second Claude OneDrive/Second Claude/raw/resumenes/*.md y wiki/*/*.md

Cada documento se convierte en una FICHA con el mismo esquema (cerebro, tipo,
fecha, titulo, personas, tickets, claves, texto, ruta) y sus secciones de
decisiones, pendientes, problemas, conocimiento y compromisos se trocean en
ATOMOS, que se indexan por separado para que una busqueda devuelva la frase
exacta y su ficha. No llama a ningun modelo.

Los cerebros son la fuente de verdad. El indice (indice.db, SQLite FTS5 con
BM25) es derivado: se reconstruye entero en segundos y se rehace solo cuando
cambia alguna fuente. La fecha solo desempata: un acuerdo antiguo no caduca
por ser antiguo.

Comandos:
    sync                    reconstruye el indice
    status                  fichas y atomos por cerebro y tipo
    search <consulta>       busca (filtros: --cerebro --tipo --desde --hasta)
    ticket <numero>         todo lo que dicen los tres cerebros de un ticket
    show <id>               ficha completa con sus atomos y rutas
    grep <regex>            texto literal en transcripciones y fuentes, con [MM:SS]
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sqlite3
import sys
import time
import unicodedata

# --- configuracion --------------------------------------------------------------

ONEDRIVE = os.path.join(os.path.expanduser("~"), "OneDrive - FORTIA ENERGIA S.L")
KNOW = os.path.join(ONEDRIVE, "Cajon", "Know")
SECONDB = os.path.join(ONEDRIVE, "SecondB", "Control Servicio EMS")
SECOND_CLAUDE = os.path.join(ONEDRIVE, "Second Claude")
INDICE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "indice.db")

TOKENIZER = "unicode61 remove_diacritics 2 tokenchars '_'"
PESOS = (6.0, 3.0, 1.0)          # bm25: titulo, claves, texto
MAX_ATOMO = 1500

# Clase de una seccion H2 segun su encabezado (sin acentos, minusculas). Orden: la primera que casa.
CLASES = [
    ("descartar", r"cautela|caveat|notas? (sobre la |de )?transcrip|aviso|advertencia|captura"
                  r"|material|lectura|fichero|participante|relacion con otras|^indice|^frames|^temas:"),
    ("cierre", r"compromisos que se cierran"),
    ("decision", r"decision|acuerdo"),
    ("pendiente", r"pendiente|accion|compromisos que salen|riesgo|que falta"),
    ("problema", r"problema"),
    ("conocimiento", r"conocimiento|ampliacion"),
    ("propuesta", r"propuesta"),
]

STOP = set("""a al algo algun alguna algunas alguno algunos ante antes aqui asi aun cada como con contra
cual cuales cuando de del desde donde dos e el ella ellas ellos en entre era es esa esas ese eso esos
esta estaba estado estan estar este esto estos fue fueron ha habia han hay la las le les lo los mas
me mi muy nada ni no nos o otra otras otro otros para pero poco por porque que quien se ser si sin
sobre son su sus tambien tiene todo todos tras tu un una unas uno unos y ya yo qué cómo cuándo dónde""".split())

TICKET_RE = re.compile(
    r"(?<![\d.,/:-])#?(2\d{4})(?![\d.,/:-])"
    r"(?!\s*(?:€|%|eur|mw|kw|kb|mb|ms|h\b|horas|segund|minut|filas|registros|bytes|lineas|caracteres))",
    re.IGNORECASE)
TS_RE = re.compile(r"^\s*\[~?(\d{1,2}:\d{2}(?::\d{2})?)\]")
FECHA_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


# --- utilidades -----------------------------------------------------------------

def sin_acentos(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))


def norm(t: str) -> str:
    """minusculas, sin acentos; solo letras, digitos y _ (como el tokenizador)."""
    return " ".join(re.sub(r"[^0-9a-z_]+", " ", sin_acentos(t).lower()).split())


def leer(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def limpiar_md(t: str) -> str:
    t = re.sub(r"<!--.*?-->", " ", t, flags=re.S)
    t = re.sub(r"\]\([^)]*\)", "]", t)          # enlaces: se queda el texto
    return t


def tickets_de(texto: str) -> list[str]:
    return sorted(set(TICKET_RE.findall(texto)))


def titulo_h1(md: str, defecto: str) -> str:
    m = re.search(r"^#\s+(.+)$", md, re.M)
    return m.group(1).strip() if m else defecto


def secciones(md: str) -> list[tuple[str, str]]:
    """(encabezado H2, cuerpo). Lo anterior al primer H2 va con encabezado ''."""
    out, actual, buf = [], "", []
    for line in md.splitlines():
        if line.startswith("## "):
            out.append((actual, "\n".join(buf)))
            actual, buf = line[3:].strip(), []
        elif not line.startswith("# "):
            buf.append(line)
    out.append((actual, "\n".join(buf)))
    return [(h, b) for h, b in out if b.strip() or h]


def clase_de(encabezado: str) -> str | None:
    h = norm(encabezado)
    for clase, patron in CLASES:
        if re.search(patron, h):
            return clase
    return None


def trocear(cuerpo: str) -> list[str]:
    """Atomos de una seccion: cada punto de lista (con sus sublineas), cada fila de
    tabla y cada parrafo suelto."""
    atomos, actual = [], []

    def cerrar():
        if actual:
            t = " ".join(x.strip() for x in actual).strip()
            if len(norm(t)) > 3:
                atomos.append(t[:MAX_ATOMO])
            actual.clear()

    for line in cuerpo.splitlines():
        s = line.strip()
        if not s or re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", s):     # linea en blanco o separador
            cerrar()
            continue
        if s.startswith("|"):
            cerrar()
            celdas = [c.strip() for c in s.strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) for c in celdas if c):
                continue                                   # separador de tabla
            atomos.append(" · ".join(c for c in celdas if c))
            continue
        nuevo = re.match(r"^(?:[-*+]|\d+[.)])\s+", s)
        if nuevo and line[:1] not in (" ", "\t"):
            cerrar()
            actual.append(s[nuevo.end():])
        else:
            actual.append(re.sub(r"^(?:[-*+]|\d+[.)])\s+", "", s))
    cerrar()
    return atomos


def quitar_cabeceras_tabla(cuerpo: str) -> str:
    """Elimina la fila de cabecera de cada tabla markdown (la que precede a |---|)."""
    lineas = cuerpo.splitlines()
    fuera = set()
    for i, l in enumerate(lineas):
        if re.fullmatch(r"\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*", l) and i > 0:
            fuera.add(i - 1)
    return "\n".join(l for i, l in enumerate(lineas) if i not in fuera)


def ficha_desde_md(md: str, base: dict) -> dict:
    """Rellena texto y atomos de una ficha a partir de su markdown, por secciones."""
    md = limpiar_md(md)
    texto, atomos = [], []
    for enc, cuerpo in secciones(md):
        clase = clase_de(enc) if enc else None
        if clase == "descartar":
            continue
        if clase:
            for a in trocear(quitar_cabeceras_tabla(cuerpo)):
                atomos.append((clase, a))
        else:
            texto.append(f"{enc}\n{cuerpo}" if enc else cuerpo)
    f = dict(base)
    f["texto"] = "\n".join(texto).strip()
    f["atomos"] = base.get("atomos", []) + atomos
    todo = f["texto"] + " " + " ".join(a for _, a in f["atomos"]) + " " + " ".join(f.get("claves", []))
    f["tickets"] = sorted(set(f.get("tickets", [])) | set(tickets_de(todo)))
    return f


def nueva(id_: str, cerebro: str, tipo: str, fecha: str | None, titulo: str, ruta: str,
          **kw) -> dict:
    f = {"id": id_, "cerebro": cerebro, "tipo": tipo, "fecha": fecha or "", "titulo": titulo,
         "ruta": ruta, "personas": [], "tickets": [], "claves": [], "detalle": [],
         "texto": "", "atomos": []}
    f.update(kw)
    return f


# --- adaptadores ----------------------------------------------------------------

def adaptar_know(raiz: str) -> list[dict]:
    out = []
    if not os.path.isdir(raiz):
        return out
    for nombre in sorted(os.listdir(raiz)):
        carpeta = os.path.join(raiz, nombre)
        if nombre.startswith(("_", ".")) or not os.path.isdir(carpeta):
            continue
        ficheros = os.listdir(carpeta)
        resumen = next((f for f in ("summary.md", "resumen.md") if f in ficheros), None)
        meta = {}
        if "meta.json" in ficheros:
            try:
                meta = json.loads(leer(os.path.join(carpeta, "meta.json")))
            except ValueError:
                meta = {}
        md = leer(os.path.join(carpeta, resumen)) if resumen else ""
        if not md and not meta:
            continue
        fecha = meta.get("fecha") or (FECHA_RE.match(nombre).group(1) if FECHA_RE.match(nombre) else "")
        detalle = [os.path.join(carpeta, f) for f in ficheros
                   if f == "report.md" or ("transcrip" in f.lower() and f.endswith((".md", ".txt")))]
        base = nueva(f"know:{nombre}", "know",
                     "documento" if meta.get("tipo") == "agrupacion-documental" else "reunion",
                     fecha, meta.get("titulo") or titulo_h1(md, nombre),
                     os.path.join(carpeta, resumen) if resumen else carpeta,
                     personas=[str(p) for p in meta.get("participantes") or []],
                     claves=[str(x) for x in (meta.get("temas") or []) + (meta.get("terminos") or [])],
                     detalle=detalle)
        out.append(ficha_desde_md(md, base))
    return out


def _csv(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def adaptar_secondb(raiz: str) -> list[dict]:
    out = []
    memoria = os.path.join(raiz, "memoria")
    if not os.path.isdir(memoria):
        return out
    # reuniones de seguimiento
    rdir = os.path.join(memoria, "reuniones")
    for f in sorted(os.listdir(rdir)) if os.path.isdir(rdir) else []:
        if not f.endswith(".md") or f.startswith("_"):
            continue
        rid = f[:-3]
        md = leer(os.path.join(rdir, f))
        trans = os.path.join(raiz, "reuniones", rid, f"transcripcion-{rid}.md")
        base = nueva(f"secondb:reunion:{rid}", "secondb", "seguimiento", rid[:10],
                     titulo_h1(md, rid), os.path.join(rdir, f),
                     claves=[rid[11:]], detalle=[trans] if os.path.exists(trans) else [])
        out.append(ficha_desde_md(md, base))

    # tickets: pagina (si la tiene) + historial + acuerdos con su estado
    historial, acuerdos = {}, {}
    for r in _csv(os.path.join(memoria, "historial_tickets.csv")):
        historial.setdefault(r["ticket"], []).append(r)
    for r in _csv(os.path.join(memoria, "acuerdos.csv")):
        acuerdos.setdefault(r["ticket"], []).append(r)
    tdir = os.path.join(memoria, "tickets")
    paginas = {f[:-3]: os.path.join(tdir, f) for f in os.listdir(tdir)
               if f.endswith(".md")} if os.path.isdir(tdir) else {}
    for t in sorted(set(historial) | set(acuerdos) | set(paginas)):
        hs = sorted(historial.get(t, []), key=lambda r: r["fecha_reunion"])
        lineas = [f"{r['fecha_reunion']} ({r['sistema']}): {r['que_se_dijo']}" for r in hs]
        atomos = [("compromiso", f"{a['fecha_reunion']} · {a['acuerdo']} · {a['organizacion']}"
                                 f"{' · ' + a['persona'] if a['persona'] else ''}"
                                 f" · plazo: {a['plazo'] or 'sin plazo'} · estado: {a['estado']}")
                  for a in sorted(acuerdos.get(t, []), key=lambda r: r["fecha_reunion"])]
        fechas = [r["fecha_reunion"] for r in hs + acuerdos.get(t, [])]
        personas = sorted({p.strip() for r in hs for p in re.split(r"[;,]", r["personas"]) if p.strip()})
        md = leer(paginas[t]) if t in paginas else ""
        titulo = titulo_h1(md, f"Ticket {t}")
        if hs:
            titulo += " — " + hs[-1]["que_se_dijo"][:90]
        base = nueva(f"secondb:ticket:{t}", "secondb", "ticket", max(fechas) if fechas else "",
                     titulo, paginas.get(t, os.path.join(memoria, "historial_tickets.csv")),
                     personas=personas, tickets=[t], atomos=atomos)
        f = ficha_desde_md(md, base)
        f["texto"] = (f["texto"] + "\n" + "\n".join(lineas)).strip()
        out.append(f)

    # temas sin ticket, agregados por identificador
    temas = {}
    for r in _csv(os.path.join(memoria, "temas.csv")):
        temas.setdefault(r["tema"], []).append(r)
    for tema, rs in sorted(temas.items()):
        rs.sort(key=lambda r: r["fecha_reunion"])
        texto = "\n".join(f"{r['fecha_reunion']} ({r['sistema']}): {r['que_se_dijo']}"
                          f" [desenlace: {r['desenlace']}]" for r in rs)
        tks = {x for r in rs for x in (r.get("ticket_derivado"), r.get("ticket_cuarentena")) if x}
        out.append(nueva(f"secondb:tema:{tema}", "secondb", "tema", rs[-1]["fecha_reunion"],
                         rs[-1]["titulo"], os.path.join(memoria, "temas.csv"),
                         personas=sorted({p.strip() for r in rs for p in re.split(r"[;,]", r["personas"])
                                          if p.strip()}),
                         tickets=sorted(tks | set(tickets_de(texto))), claves=[tema.replace("-", " ")],
                         texto=texto))
    return out


def adaptar_second_claude(raiz: str) -> list[dict]:
    out = []
    rdir = os.path.join(raiz, "raw", "resumenes")
    for f in sorted(os.listdir(rdir)) if os.path.isdir(rdir) else []:
        if not f.endswith(".md"):
            continue
        md = leer(os.path.join(rdir, f))
        cab = "\n".join(md.splitlines()[:5])
        if re.search(r"^Relevancia:\s*descartar", cab, re.M | re.I):
            continue
        fm = re.search(r"Fechas:\s*(\d{4}-\d{2}-\d{2})", cab)
        pm = re.search(r"Proyecto:\s*([^·\n]+)", cab)
        claves = [pm.group(1).strip()] if pm else []
        tm = re.search(r"^##\s*Temas:(.*)$", md, re.M)
        if tm:
            claves += [x.strip() for x in re.split(r"[,;]|Entidades:|Proyecto wiki:", tm.group(1)) if x.strip()]
        sesion = os.path.join(raiz, "raw", "sesiones", f)
        base = nueva(f"sc:resumen:{f[:-3]}", "second-claude", "sesion",
                     fm.group(1) if fm else (FECHA_RE.match(f).group(1) if FECHA_RE.match(f) else ""),
                     titulo_h1(md, f[:-3]), os.path.join(rdir, f), claves=claves,
                     detalle=[sesion] if os.path.exists(sesion) else [])
        out.append(ficha_desde_md("\n".join(md.splitlines()[3:]), base))
    wdir = os.path.join(raiz, "wiki")
    for sub in sorted(os.listdir(wdir)) if os.path.isdir(wdir) else []:
        d = os.path.join(wdir, sub)
        for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
            if not f.endswith(".md"):
                continue
            md = leer(os.path.join(d, f))
            am = re.search(r"Actualizado:\s*(\d{4}-\d{2}-\d{2})", md)
            singular = {"proyectos": "proyecto", "temas": "tema", "entidades": "entidad"}.get(sub, sub)
            base = nueva(f"sc:wiki:{sub}/{f[:-3]}", "second-claude", f"wiki-{singular}",
                         am.group(1) if am else "", titulo_h1(md, f[:-3]), os.path.join(d, f),
                         claves=[f[:-3].replace("-", " ")])
            out.append(ficha_desde_md(md, base))
    return out


def todas_las_fichas() -> list[dict]:
    return adaptar_know(KNOW) + adaptar_secondb(SECONDB) + adaptar_second_claude(SECOND_CLAUDE)


# --- indice ---------------------------------------------------------------------

def firma_fuentes() -> str:
    """Cuantos ficheros fuente hay y cuando cambio el ultimo: si no coincide, se rehace."""
    know, secondb, second_claude = KNOW, SECONDB, SECOND_CLAUDE
    n, ultimo = 0, 0
    rutas = []
    if os.path.isdir(know):
        for d in os.listdir(know):
            for f in ("summary.md", "resumen.md", "meta.json"):
                rutas.append(os.path.join(know, d, f))
            rutas.append(os.path.join(know, d))          # altas y bajas de carpetas
    for sub in ("reuniones", "tickets"):
        d = os.path.join(secondb, "memoria", sub)
        rutas += [os.path.join(d, f) for f in (os.listdir(d) if os.path.isdir(d) else [])]
    rutas += [os.path.join(secondb, "memoria", f) for f in
              ("historial_tickets.csv", "acuerdos.csv", "temas.csv")]
    d = os.path.join(second_claude, "raw", "resumenes")
    rutas += [os.path.join(d, f) for f in (os.listdir(d) if os.path.isdir(d) else [])]
    w = os.path.join(second_claude, "wiki")
    for sub in os.listdir(w) if os.path.isdir(w) else []:
        dd = os.path.join(w, sub)
        rutas += [os.path.join(dd, f) for f in (os.listdir(dd) if os.path.isdir(dd) else [])]
    for r in rutas:
        try:
            st = os.stat(r)
        except OSError:
            continue
        n += 1
        ultimo = max(ultimo, st.st_mtime_ns)
    return f"{n}:{ultimo}"


def construir(db: str | None = None, fichas: list[dict] | None = None, firma: str = "") -> dict:
    db = db or INDICE
    t0 = time.time()
    fichas = todas_las_fichas() if fichas is None else fichas
    tmp = db + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    con = sqlite3.connect(tmp)
    con.executescript(f"""
        CREATE TABLE fichas(id TEXT PRIMARY KEY, cerebro TEXT, tipo TEXT, fecha TEXT, titulo TEXT,
            personas TEXT, tickets TEXT, claves TEXT, ruta TEXT, detalle TEXT, texto TEXT);
        CREATE TABLE atomos(rid INTEGER PRIMARY KEY, ficha TEXT, clase TEXT, texto TEXT, tickets TEXT);
        CREATE VIRTUAL TABLE fts USING fts5(titulo, claves, texto, tipo UNINDEXED, ref UNINDEXED,
            tokenize="{TOKENIZER}");
        CREATE TABLE info(clave TEXT PRIMARY KEY, valor TEXT);
    """)
    n_atomos = 0
    for f in fichas:
        con.execute("INSERT INTO fichas VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (f["id"], f["cerebro"], f["tipo"], f["fecha"], f["titulo"],
                     json.dumps(f["personas"], ensure_ascii=False), " ".join(f["tickets"]),
                     json.dumps(f["claves"], ensure_ascii=False), f["ruta"],
                     json.dumps(f["detalle"], ensure_ascii=False), f["texto"]))
        con.execute("INSERT INTO fts VALUES(?,?,?,?,?)",
                    (f["titulo"], " ".join(f["claves"] + f["personas"] + f["tickets"]),
                     f["texto"], "ficha", f["id"]))
        for clase, texto in f["atomos"]:
            tks = " ".join(tickets_de(texto))
            cur = con.execute("INSERT INTO atomos(ficha, clase, texto, tickets) VALUES(?,?,?,?)",
                              (f["id"], clase, texto, tks))
            con.execute("INSERT INTO fts VALUES(?,?,?,?,?)",
                        (f["titulo"], f"{clase} {tks}", texto, "atomo", str(cur.lastrowid)))
            n_atomos += 1
    info = {"generado": time.strftime("%Y-%m-%dT%H:%M:%S"), "firma": firma or firma_fuentes(),
            "fichas": str(len(fichas)), "atomos": str(n_atomos),
            "segundos": f"{time.time() - t0:.1f}"}
    con.executemany("INSERT INTO info VALUES(?,?)", info.items())
    con.commit()
    con.close()
    os.replace(tmp, db)
    return info


def abrir(db: str | None = None, fresco: bool = True) -> sqlite3.Connection:
    """Abre el indice; lo rehace antes si no existe o si alguna fuente ha cambiado."""
    db = db or INDICE
    if fresco:
        firma = firma_fuentes()
        actual = None
        if os.path.exists(db):
            try:
                c = sqlite3.connect(db)
                actual = c.execute("SELECT valor FROM info WHERE clave='firma'").fetchone()
                c.close()
            except sqlite3.Error:
                actual = None
        if not actual or actual[0] != firma:
            construir(db, firma=firma)
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    return con


# --- consulta -------------------------------------------------------------------

def cargar_alias() -> list[list[str]]:
    try:
        data = json.loads(leer(os.path.join(KNOW, "_kb", "aliases.json")))
    except (OSError, ValueError):
        return []
    grupos = data.get("grupos") if isinstance(data, dict) else data
    return [[norm(x) for x in g if norm(x)] for g in grupos or [] if isinstance(g, list)]


def _variante(v: str) -> str:
    v = v.replace('"', "")
    if " " in v:
        return f'"{v}"'
    return f'"{v}"*' if len(v) >= 5 and not v.isdigit() else f'"{v}"'


def unidades_de(texto: str, grupos: list[list[str]]) -> list[list[str]]:
    """Terminos de la consulta, cada uno con sus alias (frases de alias incluidas)."""
    q = norm(texto)
    unidades = []
    multi = sorted({v for g in grupos for v in g if " " in v}, key=len, reverse=True)
    for v in multi:
        if re.search(rf"(?<![0-9a-z_]){re.escape(v)}(?![0-9a-z_])", q):
            grupo = next(g for g in grupos if v in g)
            unidades.append(grupo)
            q = re.sub(rf"(?<![0-9a-z_]){re.escape(v)}(?![0-9a-z_])", " ", q)
    for tok in q.split():
        if tok in STOP or len(tok) < 2:
            continue
        grupo = next((g for g in grupos if tok in g), [tok])
        unidades.append(grupo if tok in grupo else [tok] + grupo)
    return unidades


def consulta_fts(texto: str, grupos: list[list[str]]) -> str:
    """Consulta FTS5: cada termino con sus alias y prefijo en las palabras largas,
    terminos unidos por OR (el orden lo decide luego la cobertura y BM25)."""
    partes = []
    for u in unidades_de(texto, grupos):
        vs = sorted(set(u))
        partes.append("(" + " OR ".join(_variante(v) for v in vs) + ")" if len(vs) > 1 else _variante(vs[0]))
    return " OR ".join(partes)


def cobertura(texto_norm: str, unidades: list[list[str]]) -> int:
    """Cuantos terminos de la consulta aparecen (por palabra o prefijo) en un texto."""
    n = 0
    for u in unidades:
        for v in u:
            fin = "" if len(v) >= 5 and " " not in v else r"(?![0-9a-z_])"
            if re.search(rf"(?<![0-9a-z_]){re.escape(v)}{fin}", texto_norm):
                n += 1
                break
    return n


def buscar(con: sqlite3.Connection, texto: str, cerebro: str | None = None, tipo: str | None = None,
           desde: str | None = None, hasta: str | None = None, limite: int = 10,
           grupos: list[list[str]] | None = None) -> list[dict]:
    grupos = cargar_alias() if grupos is None else grupos
    unidades = unidades_de(texto, grupos)
    q = consulta_fts(texto, grupos)
    if not q:
        return []
    filas = con.execute(
        "SELECT tipo, ref, bm25(fts, ?, ?, ?) AS s, titulo, claves, texto FROM fts "
        "WHERE fts MATCH ? ORDER BY s LIMIT 400", (*PESOS, q)).fetchall()
    res: dict[str, dict] = {}
    for kind, ref, s, t_titulo, t_claves, t_texto in filas:
        # Una ficha cubre por su titulo y claves; un atomo, solo por su propio texto. El texto
        # corrido de una ficha no cuenta: un resumen largo "cubriria" cualquier cosa.
        cob = cobertura(norm(t_texto if kind == "atomo" else f"{t_titulo} {t_claves}"), unidades)
        if kind == "atomo":
            a = con.execute("SELECT * FROM atomos WHERE rid=?", (int(ref),)).fetchone()
            fid = a["ficha"]
        else:
            a, fid = None, ref
        if fid not in res:
            f = con.execute("SELECT * FROM fichas WHERE id=?", (fid,)).fetchone()
            if (cerebro and f["cerebro"] != cerebro) or (tipo and not f["tipo"].startswith(tipo)) \
                    or (desde and f["fecha"] < desde) or (hasta and f["fecha"] > hasta):
                res[fid] = None
                continue
            res[fid] = {"id": fid, "cerebro": f["cerebro"], "tipo": f["tipo"], "fecha": f["fecha"],
                        "titulo": f["titulo"], "ruta": f["ruta"], "score": s, "cobertura": cob,
                        "terminos": len(unidades), "atomos": []}
        r = res[fid]
        if r is None:
            continue
        r["score"] = min(r["score"], s)
        r["cobertura"] = max(r["cobertura"], cob)
        if a is not None:
            r["atomos"].append({"clase": a["clase"], "texto": a["texto"], "_cob": cob, "_s": s})
    hits = [r for r in res.values() if r]
    for r in hits:      # los atomos que mas terminos cubren, primero
        r["atomos"] = [{"clase": a["clase"], "texto": a["texto"]}
                       for a in sorted(r["atomos"], key=lambda a: (-a["_cob"], a["_s"]))[:3]]
    # Manda la cobertura (terminos de la consulta en una misma ficha o atomo), luego BM25;
    # la fecha (mas reciente primero) solo desempata.
    hits.sort(key=lambda r: (-r["cobertura"], round(r["score"], 1), tuple(-ord(c) for c in r["fecha"])))
    return hits[:limite]


def por_ticket(con: sqlite3.Connection, numero: str) -> list[dict]:
    out = []
    for f in con.execute("SELECT * FROM fichas WHERE ' ' || tickets || ' ' LIKE ? ORDER BY fecha",
                         (f"% {numero} %",)):
        atomos = [dict(a) for a in con.execute(
            "SELECT clase, texto FROM atomos WHERE ficha=? AND ' ' || tickets || ' ' LIKE ?",
            (f["id"], f"% {numero} %"))]
        out.append({"id": f["id"], "cerebro": f["cerebro"], "tipo": f["tipo"], "fecha": f["fecha"],
                    "titulo": f["titulo"], "ruta": f["ruta"], "atomos": atomos})
    return out


def ficha(con: sqlite3.Connection, fid: str) -> dict | None:
    f = con.execute("SELECT * FROM fichas WHERE id=?", (fid,)).fetchone()
    if not f:
        return None
    d = dict(f)
    for k in ("personas", "claves", "detalle"):
        d[k] = json.loads(d[k])
    d["atomos"] = [dict(a) for a in con.execute(
        "SELECT clase, texto FROM atomos WHERE ficha=? ORDER BY rid", (fid,))]
    return d


def fuentes_grep(ambito="todo"):
    """Ficheros para grep: transcripciones (literales) y, con ambito=todo, tambien las fuentes."""
    know, secondb, second_claude = KNOW, SECONDB, SECOND_CLAUDE
    if os.path.isdir(know):
        for d in sorted(os.listdir(know)):
            c = os.path.join(know, d)
            if d.startswith(("_", ".")) or not os.path.isdir(c):
                continue
            for f in sorted(os.listdir(c)):
                tr = f == "report.md" or ("transcrip" in f.lower() and f.endswith((".md", ".txt")))
                if tr or (ambito == "todo" and f in ("summary.md", "resumen.md")):
                    yield "know", os.path.join(c, f)
    r = os.path.join(secondb, "reuniones")
    for d in sorted(os.listdir(r)) if os.path.isdir(r) else []:
        p = os.path.join(r, d, f"transcripcion-{d}.md")
        if os.path.exists(p):
            yield "secondb", p
    if ambito == "todo":
        for sub in ("reuniones", "tickets"):
            dd = os.path.join(secondb, "memoria", sub)
            for f in sorted(os.listdir(dd)) if os.path.isdir(dd) else []:
                yield "secondb", os.path.join(dd, f)
        s = os.path.join(second_claude, "raw", "sesiones")
        for f in sorted(os.listdir(s)) if os.path.isdir(s) else []:
            yield "second-claude", os.path.join(s, f)


def grep(patron: str, ambito: str = "todo", limite: int = 50, cerebro: str | None = None) -> list[dict]:
    rx = re.compile(patron, re.IGNORECASE)
    out = []
    for cer, path in fuentes_grep(ambito=ambito):
        if cerebro and cer != cerebro:
            continue
        try:
            lineas = leer(path).splitlines()
        except OSError:
            continue
        ts = ""
        for i, l in enumerate(lineas, 1):
            m = TS_RE.match(l)
            if m:
                ts = m.group(1)
            if rx.search(l):
                exacto = bool(m)
                out.append({"cerebro": cer, "ruta": path, "linea": i,
                            "ts": (ts if exacto else (f"~{ts}" if ts else "")),
                            "texto": l.strip()[:300]})
                if len(out) >= limite:
                    return out
    return out


# --- comandos -------------------------------------------------------------------

def _salida(obj, como_json: bool, texto_fn) -> int:
    if como_json:
        print(json.dumps(obj, ensure_ascii=False, indent=1))
    else:
        texto_fn(obj)
    return 0


def cmd_sync(args) -> int:
    info = construir(args.db)
    print(f"indice: {info['fichas']} fichas, {info['atomos']} atomos en {info['segundos']} s -> {args.db or INDICE}")
    return 0


def cmd_status(args) -> int:
    con = abrir(args.db)
    info = dict(con.execute("SELECT clave, valor FROM info").fetchall())
    print(f"indice: {args.db}\ngenerado: {info['generado']} ({info['segundos']} s)")
    for r in con.execute("SELECT cerebro, tipo, count(*) n FROM fichas GROUP BY 1,2 ORDER BY 1,2"):
        print(f"  {r['cerebro']:<14} {r['tipo']:<16} {r['n']:>4}")
    for r in con.execute("SELECT clase, count(*) n FROM atomos GROUP BY 1 ORDER BY 2 DESC"):
        print(f"  atomo {r['clase']:<14} {r['n']:>5}")
    sin_fecha = con.execute("SELECT count(*) FROM fichas WHERE fecha=''").fetchone()[0]
    if sin_fecha:
        print(f"!! {sin_fecha} ficha(s) sin fecha")
    return 0


def _imprimir_hits(hits):
    if not hits:
        print("sin resultados")
    for h in hits:
        print(f"\n[{h['cerebro']}] {h['fecha'] or 'sin fecha'} · {h['tipo']} · {h['titulo']}")
        print(f"  id: {h['id']}")
        print(f"  {h['ruta']}")
        for a in h["atomos"]:
            print(f"  - ({a['clase']}) {a['texto'][:240]}")


def cmd_search(args) -> int:
    con = abrir(args.db)
    hits = buscar(con, " ".join(args.consulta), args.cerebro, args.tipo, args.desde, args.hasta,
                  args.limit)
    return _salida(hits, args.json, _imprimir_hits)


def cmd_ticket(args) -> int:
    con = abrir(args.db)
    hits = por_ticket(con, args.numero.lstrip("#"))

    def txt(hs):
        if not hs:
            print(f"ningun cerebro menciona el ticket {args.numero}")
        _imprimir_hits(hs)
        print("\n(Para su estado actual en Redmine, consultar AgenteRed.)")
    return _salida(hits, args.json, txt)


def cmd_show(args) -> int:
    con = abrir(args.db)
    f = ficha(con, args.id)
    if not f:
        print(f"no existe la ficha {args.id}")
        return 1

    def txt(f):
        print(f"{f['titulo']}\n[{f['cerebro']}] {f['tipo']} · {f['fecha'] or 'sin fecha'} · id: {f['id']}")
        print(f"fuente: {f['ruta']}")
        for d in f["detalle"]:
            print(f"detalle: {d}")
        if f["personas"]:
            print("personas: " + ", ".join(f["personas"]))
        if f["tickets"]:
            print("tickets: " + f["tickets"])
        clase = None
        for a in f["atomos"]:
            if a["clase"] != clase:
                clase = a["clase"]
                print(f"\n{clase}:")
            print(f"  - {a['texto'][:400]}")
    return _salida(f, args.json, txt)


def cmd_grep(args) -> int:
    hits = grep(args.patron, args.ambito, args.limit, args.cerebro)

    def txt(hs):
        for h in hs:
            ts = f" [{h['ts']}]" if h["ts"] else ""
            print(f"{h['ruta']}:{h['linea']}{ts}  {h['texto']}")
        if len(hs) >= args.limit:
            print(f"(limite de {args.limit}; amplia con --limit)")
    return _salida(hits, args.json, txt)


def main(argv=None) -> int:
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=None, help="ruta del indice (defecto: indice.db junto al script)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("sync")
    p.set_defaults(fn=cmd_sync)
    p = sub.add_parser("status")
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("search")
    p.add_argument("consulta", nargs="+")
    p.add_argument("--cerebro", choices=["know", "secondb", "second-claude"])
    p.add_argument("--tipo", help="reunion, documento, seguimiento, ticket, tema, sesion, wiki")
    p.add_argument("--desde")
    p.add_argument("--hasta")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_search)

    p = sub.add_parser("ticket")
    p.add_argument("numero")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_ticket)

    p = sub.add_parser("show")
    p.add_argument("id")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_show)

    p = sub.add_parser("grep")
    p.add_argument("patron", help="expresion regular, sin distinguir mayusculas")
    p.add_argument("--ambito", choices=["transcripciones", "todo"], default="todo")
    p.add_argument("--cerebro", choices=["know", "secondb", "second-claude"])
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_grep)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
