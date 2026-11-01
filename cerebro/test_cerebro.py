#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pruebas de cerebro.py. SOLO trabajan sobre carpetas temporales con tres
cerebros de juguete; no leen OneDrive ni tocan el indice real.

    python cerebro/test_cerebro.py
"""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cerebro as cb  # noqa: E402


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


RESUMEN_KNOW = """# Seguimiento Business Central

**Fecha:** 2026-10-28

## Titular

Se revisa la carga de clientes en BC y el paralelo de diciembre.

## Decisiones confirmadas

1. El arranque es en **enero de 2027**.
2. La contingencia de Intermoney se hace a mano el 4 de enero
   (ticket 27801).

## Pendientes

| # | Pendiente | Responsable | Fecha |
|---|---|---|---|
| 1 | Probar las titulizaciones en el paralelo | Kiko | Diciembre |

---

## Cautelas de la transcripción

- "Intermoni" = Intermoney.
"""

PAGINA_SEG = """# Reunión de seguimiento — 2026-10-29 · EMS

## Lo tratado

Repaso de la habilitación de robots de OMIE por web service.

## Compromisos que salen

- 27795: documentarse sobre el error que devuelve OMIE. Proveedor · **sin plazo**.

## Lecturas

- Nada.
"""

RESUMEN_SC = """# Función de reparto del continuo
Sesión: abc · Proyecto: ems · Fechas: 2026-10-12 10:00–2026-10-12 11:00 · Fuente: [raw](../sesiones/x.md)
Relevancia: alta — análisis del MIC96

## Qué se hizo
Se revisó la función de reparto FUN_CONS_PREV_MIC_ENER_ASIG.

## Decisiones (y por qué)
- Separar la vista V_ROB_PREVISIONES de la función, porque la vista ya está resuelta.

## Problemas y soluciones
- La función de reparto duplicaba energía del continuo (#27703) → se toma el periodo de la ronda.

## Temas: MIC96, SRAD   Entidades: FUN_CONS   Proyecto wiki: mic96
"""

DESCARTADO = """# Prueba sin interés
Sesión: zzz · Proyecto: x · Fechas: 2026-10-01 10:00–2026-10-01 10:05 · Fuente: [raw](../sesiones/y.md)
Relevancia: descartar — charla

"""

WIKI = """# Programa SRAD

Tipo: tema · Actualizado: 2026-10-28 · Relacionado: [x](../x.md)

## Resumen
Cómo calcula el EMS el programa SRAD.

## Conocimiento
- El programa SRAD depende de la función de asignación del MIC ([fuente](../../raw/resumenes/x.md)).

## Pendientes / abierto
- Confirmar si arreglar la función basta.
"""


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cerebro-test-")
        self._rutas = (cb.KNOW, cb.SECONDB, cb.SECOND_CLAUDE, cb.INDICE)
        cb.KNOW = os.path.join(self.tmp, "Know")
        cb.SECONDB = os.path.join(self.tmp, "SecondB")
        cb.SECOND_CLAUDE = os.path.join(self.tmp, "SC")
        cb.INDICE = os.path.join(self.tmp, "indice.db")
        k = cb.KNOW
        write(os.path.join(k, "2026-10-28 Seg Business Central", "summary.md"), RESUMEN_KNOW)
        write(os.path.join(k, "2026-10-28 Seg Business Central", "meta.json"), json.dumps(
            {"fecha": "2026-10-28", "titulo": "Seguimiento proyecto Business Central",
             "participantes": ["Antonio", "Kiko"], "temas": ["Paralelo de diciembre"],
             "terminos": ["Intermoney", "titulizaciones"]}))
        write(os.path.join(k, "2026-10-28 Seg Business Central", "report.md"),
              "# watch\n\n## Transcript\n\n```\n[00:05] Hola.\n[12:40] Lo de Intermoney lo hacemos a mano.\n"
              "y sigue hablando de Intermoney sin marca\n```\n")
        write(os.path.join(k, "_retiradas", "2026-09-10 Seg EMS", "summary.md"), "# Duplicada\n\nIntermoney\n")
        write(os.path.join(k, "_kb", "aliases.json"), json.dumps(
            {"grupos": [["Business Central", "BC"], ["Intermoney", "Intermoni"]]}))
        m = os.path.join(cb.SECONDB, "memoria")
        write(os.path.join(m, "reuniones", "2026-10-29-EMS.md"), PAGINA_SEG)
        write(os.path.join(m, "reuniones", "_plantilla.md"), "# Plantilla\n")
        write(os.path.join(cb.SECONDB, "reuniones", "2026-10-29-EMS", "transcripcion-2026-10-29-EMS.md"),
              "[11:10] El 27795 es lo de OMIE.\n")
        write(os.path.join(m, "tickets", "27795.md"),
              "# Ticket 27795\n\n## Qué falta para cerrarlo\n\nSaber qué error devuelve OMIE.\n\n## Cronología\n\n- 2026-10-29: alta.\n")
        write(os.path.join(m, "historial_tickets.csv"),
              "ticket,fecha_reunion,sistema,que_se_dijo,personas,hubo_acuerdo,relevancia,origen_relevancia,tramo,origen\n"
              "27795,2026-10-29,EMS,Adaptar las consultas por web service a OMIE,Vicente,sí,alta,inferida,00:11:10-00:11:45,grabacion\n"
              "27703,2026-09-25,EMS,Función de reparto del continuo con fallos,Javier,sí,alta,inferida,,grabacion\n")
        write(os.path.join(m, "acuerdos.csv"),
              "ticket,fecha_reunion,sistema,acuerdo,organizacion,persona,plazo,estado,origen\n"
              "27795,2026-10-29,EMS,Buscar en la documentación de OMIE el error,Proveedor,,,vivo,grabacion\n")
        write(os.path.join(m, "temas.csv"),
              "tema,fecha_reunion,sistema,tipo,titulo,que_se_dijo,personas,relevancia,origen_relevancia,"
              "desenlace,ticket_cuarentena,ticket_derivado,tramo,origen\n"
              "carburos-cinca,2026-10-29,EMS,aparicion,Usuario de centro de control de Carburos Cinca,"
              "Se dio de alta a mano,Alex,baja,inferida,abierto,,,,grabacion\n")
        s = cb.SECOND_CLAUDE
        write(os.path.join(s, "raw", "resumenes", "2026-10-12_ems_abc_x1.md"), RESUMEN_SC)
        write(os.path.join(s, "raw", "resumenes", "2026-10-01_x_zzz_x1.md"), DESCARTADO)
        write(os.path.join(s, "wiki", "temas", "programa-srad.md"), WIKI)

    def tearDown(self):
        cb.KNOW, cb.SECONDB, cb.SECOND_CLAUDE, cb.INDICE = self._rutas
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fichas(self):
        return {f["id"]: f for f in cb.todas_las_fichas()}


class TestAdaptadores(Base):
    def test_know_ficha_y_atomos_por_seccion(self):
        f = self.fichas()["know:2026-10-28 Seg Business Central"]
        self.assertEqual((f["cerebro"], f["tipo"], f["fecha"]), ("know", "reunion", "2026-10-28"))
        self.assertEqual(f["titulo"], "Seguimiento proyecto Business Central")
        self.assertEqual(f["personas"], ["Antonio", "Kiko"])
        atomos = [(c, t) for c, t in f["atomos"]]
        self.assertIn(("decision", "El arranque es en **enero de 2027**."), atomos)
        # punto de lista con su continuacion en la linea siguiente
        self.assertIn(("decision", "La contingencia de Intermoney se hace a mano el 4 de enero (ticket 27801)."), atomos)
        # fila de tabla sin la cabecera ni el separador, y sin el --- pegado
        self.assertIn(("pendiente", "1 · Probar las titulizaciones en el paralelo · Kiko · Diciembre"), atomos)
        self.assertFalse(any("Pendiente · Responsable" in t for _, t in atomos))
        self.assertEqual(f["tickets"], ["27801"])
        # las cautelas no entran ni como texto ni como atomo
        self.assertNotIn("Intermoni", f["texto"] + " ".join(t for _, t in atomos))
        self.assertIn("carga de clientes", f["texto"])

    def test_know_ignora_carpetas_de_herramienta_y_retiradas(self):
        ids = self.fichas()
        self.assertFalse([i for i in ids if "_retiradas" in i or "_kb" in i])

    def test_secondb_reunion_ticket_y_tema(self):
        fs = self.fichas()
        r = fs["secondb:reunion:2026-10-29-EMS"]
        self.assertEqual((r["tipo"], r["fecha"]), ("seguimiento", "2026-10-29"))
        self.assertIn(("pendiente", "27795: documentarse sobre el error que devuelve OMIE. Proveedor · **sin plazo**."),
                      r["atomos"])
        self.assertFalse([a for a in r["atomos"] if "Nada" in a[1]])         # Lecturas se descarta
        self.assertNotIn("secondb:reunion:_plantilla", fs)
        t = fs["secondb:ticket:27795"]
        self.assertTrue(t["titulo"].startswith("Ticket 27795 — Adaptar las consultas"))
        self.assertIn(("compromiso", "2026-10-29 · Buscar en la documentación de OMIE el error · Proveedor"
                                     " · plazo: sin plazo · estado: vivo"), t["atomos"])
        self.assertIn(("pendiente", "Saber qué error devuelve OMIE."), t["atomos"])
        self.assertEqual(t["personas"], ["Vicente"])
        # ticket solo con historial, sin pagina
        self.assertIn("secondb:ticket:27703", fs)
        self.assertEqual(fs["secondb:tema:carburos-cinca"]["titulo"],
                         "Usuario de centro de control de Carburos Cinca")

    def test_second_claude_resumen_wiki_y_descartados(self):
        fs = self.fichas()
        r = fs["sc:resumen:2026-10-12_ems_abc_x1"]
        self.assertEqual((r["tipo"], r["fecha"]), ("sesion", "2026-10-12"))
        self.assertIn("MIC96", r["claves"])
        self.assertIn("27703", r["tickets"])
        self.assertEqual({c for c, _ in r["atomos"]}, {"decision", "problema"})
        self.assertNotIn("sc:resumen:2026-10-01_x_zzz_x1", fs)
        w = fs["sc:wiki:temas/programa-srad"]
        self.assertEqual((w["tipo"], w["fecha"]), ("wiki-tema", "2026-10-28"))
        self.assertEqual({c for c, _ in w["atomos"]}, {"conocimiento", "pendiente"})


class TestIndice(Base):
    def test_busqueda_cruza_cerebros_y_devuelve_el_atomo(self):
        con = cb.abrir()
        hits = {h["id"]: h for h in cb.buscar(con, "función de reparto del continuo")[:2]}
        self.assertEqual(set(hits), {"sc:resumen:2026-10-12_ems_abc_x1", "secondb:ticket:27703"})
        self.assertIn("duplicaba energía",
                      hits["sc:resumen:2026-10-12_ems_abc_x1"]["atomos"][0]["texto"])

    def test_atomo_concreto_gana_a_resumen_largo(self):
        # un resumen que menciona todos los terminos repartidos no debe ganar por eso
        write(os.path.join(cb.KNOW, "2026-10-01 Larga", "summary.md"),
              "# Reunión larga\n\n## Titular\n\nHablamos de energía.\n\n" + "Relleno. " * 200
              + "\n\nAl final salió OMIE.\n\nY otra cosa sobre robots.\n")
        con = cb.abrir()
        ids = [h["id"] for h in cb.buscar(con, "error OMIE robots")]
        self.assertIn(ids[0], ("secondb:ticket:27795", "secondb:reunion:2026-10-29-EMS"))
        self.assertGreater(ids.index("know:2026-10-01 Larga"), 1)

    def test_alias_de_varias_palabras_y_de_una(self):
        con = cb.abrir()
        self.assertEqual(cb.buscar(con, "BC")[0]["id"], "know:2026-10-28 Seg Business Central")
        self.assertEqual(cb.buscar(con, "Intermoni")[0]["id"], "know:2026-10-28 Seg Business Central")
        self.assertEqual(cb.unidades_de("seguimiento business central", cb.cargar_alias())[0],
                         ["business central", "bc"])

    def test_filtros(self):
        con = cb.abrir()
        self.assertEqual({h["cerebro"] for h in cb.buscar(con, "OMIE", cerebro="secondb")}, {"secondb"})
        self.assertFalse([h for h in cb.buscar(con, "OMIE", desde="2026-11-01")])
        self.assertTrue(all(h["tipo"] == "ticket" for h in cb.buscar(con, "OMIE", tipo="ticket")))

    def test_ticket_reune_los_tres_cerebros_en_orden(self):
        con = cb.abrir()
        hits = cb.por_ticket(con, "27703")
        self.assertEqual([h["id"] for h in hits],
                         ["secondb:ticket:27703", "sc:resumen:2026-10-12_ems_abc_x1"])
        self.assertEqual(hits[1]["atomos"][0]["clase"], "problema")

    def test_se_rehace_solo_si_cambia_una_fuente(self):
        cb.abrir().close()
        t1 = os.path.getmtime(cb.INDICE)
        time.sleep(0.05)
        cb.abrir().close()
        self.assertEqual(os.path.getmtime(cb.INDICE), t1)
        write(os.path.join(cb.SECOND_CLAUDE, "wiki", "temas", "nuevo.md"),
              "# Tema nuevo\n\nTipo: tema · Actualizado: 2026-11-01\n\n## Conocimiento\n- Zarzaparrilla.\n")
        con = cb.abrir()
        self.assertGreater(os.path.getmtime(cb.INDICE), t1)
        self.assertEqual(cb.buscar(con, "zarzaparrilla")[0]["id"], "sc:wiki:temas/nuevo")

    def test_show(self):
        con = cb.abrir()
        f = cb.ficha(con, "know:2026-10-28 Seg Business Central")
        self.assertTrue(f["detalle"][0].endswith("report.md"))
        self.assertIsNone(cb.ficha(con, "no:existe"))


class TestGrep(Base):
    def test_marca_exacta_o_aproximada(self):
        hits = cb.grep("intermoney", ambito="transcripciones")
        self.assertEqual([(h["linea"], h["ts"]) for h in hits], [(7, "12:40"), (8, "~12:40")])
        self.assertTrue(all(h["cerebro"] == "know" for h in hits))
        todos = cb.grep("OMIE", cerebro="secondb")
        self.assertTrue(any(h["ts"] == "11:10" for h in todos))

    def test_cli(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cb.main(["search", "titulizaciones", "--json"])
        self.assertEqual(json.loads(buf.getvalue())[0]["id"], "know:2026-10-28 Seg Business Central")


if __name__ == "__main__":
    unittest.main()
