#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pruebas de salud.py. SOLO trabajan sobre carpetas temporales; no leen C:\\V,
OneDrive ni el indice real.

    python salud/test_salud.py
"""

import json
import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import salud as sa  # noqa: E402

iv = sa.iv
DIA = 86400


def write(path, text="x", edad_dias=0.0, ahora=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    envejecer(path, edad_dias, ahora)


def envejecer(path, edad_dias, ahora=None):
    t = (ahora or time.time()) - edad_dias * DIA
    os.utime(path, (t, t))


def textos(res, nivel="aviso"):
    return [r["texto"] for r in res if r["nivel"] == nivel]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="salud-")
        self.ahora = time.time()
        self.origen = os.path.join(self.tmp, "V")
        self.know = os.path.join(self.tmp, "Know")
        self.secondb = os.path.join(self.tmp, "SecondB")
        self.sc = os.path.join(self.tmp, "Second Claude")
        for d in (self.origen, self.know, self.secondb, self.sc):
            os.makedirs(d)
        self._local = iv.LOCAL
        iv.LOCAL = os.path.join(self.origen, ".ingesta")

    def tearDown(self):
        iv.LOCAL = self._local
        shutil.rmtree(self.tmp, ignore_errors=True)

    def video(self, nombre, edad_dias):
        p = os.path.join(self.origen, nombre)
        write(p, "v" * (iv.MIN_BYTES + 10), edad_dias, self.ahora)
        return p


class TestVideos(Base):
    def test_pendiente_viejo_avisa_y_reciente_no(self):
        self.video("2026-10-01 10-00-00.mkv", 5)
        self.video("2026-10-31 10-00-00.mkv", 1)
        res = sa.revisar_videos(self.origen, self.know, self.secondb, self.ahora, 2)
        avisos = textos(res)
        self.assertEqual(len(avisos), 1)
        self.assertIn("2026-10-01 10-00-00.mkv", avisos[0])
        self.assertNotIn("2026-10-31", avisos[0])

    def test_borrable_es_info_no_aviso(self):
        self.video("2026-10-01 Reunion.mkv", 10)
        carpeta = os.path.join(self.know, "2026-10-01 Reunion")
        write(os.path.join(carpeta, "report.md"), "**Source:** 2026-10-01 Reunion.mkv\n")
        write(os.path.join(carpeta, "summary.md"))
        write(os.path.join(carpeta, "meta.json"), "{}")
        res = sa.revisar_videos(self.origen, self.know, self.secondb, self.ahora, 2)
        self.assertEqual(textos(res), [])
        self.assertTrue(any("se pueden borrar" in t for t in textos(res, "info")))

    def test_bandeja_parada(self):
        self.video("2026-10-01 Reunion.mkv", 10)
        el = os.path.join(iv.LOCAL, "bandeja", "2026-10-01 Reunion")
        write(os.path.join(el, "report.md"), "**Source:** 2026-10-01 Reunion.mkv\n")
        envejecer(el, 4, self.ahora)
        res = sa.revisar_videos(self.origen, self.know, self.secondb, self.ahora, 2)
        self.assertTrue(any("bandeja" in t and "2026-10-01 Reunion" in t for t in textos(res)))

    def test_sin_origen_no_falla(self):
        res = sa.revisar_videos(os.path.join(self.tmp, "no"), self.know, self.secondb, self.ahora, 2)
        self.assertEqual(textos(res), [])


class TestReuniones(Base):
    def test_know_y_secondb_sin_consolidar(self):
        k = os.path.join(self.know, "2026-10-20 Algo")
        write(os.path.join(k, "report.md"))
        envejecer(k, 3, self.ahora)
        s = os.path.join(self.secondb, "reuniones", "2026-10-21-EMS")
        write(os.path.join(s, "transcripcion-2026-10-21-EMS.md"))
        envejecer(s, 3, self.ahora)
        reciente = os.path.join(self.know, "2026-11-01 Nueva")
        write(os.path.join(reciente, "report.md"))
        avisos = textos(sa.revisar_reuniones(self.know, self.secondb, self.ahora, 2))
        self.assertEqual(len(avisos), 2)
        self.assertIn("2026-10-20 Algo", avisos[0])
        self.assertIn("2026-10-21-EMS", avisos[1])
        self.assertFalse(any("Nueva" in t for t in avisos))


class TestKnow(Base):
    def test_flags_y_errores(self):
        status = {"sync": {"ok": False, "errores": [{"path": "X", "error": "e"}]},
                  "flags": {"meta-desactualizado": ["A", "B"], "sin-resumen": []}}
        avisos = textos(sa.avisos_know(status))
        self.assertEqual(len(avisos), 2)
        self.assertIn("errores", avisos[0])
        self.assertIn("2 reuniones con meta.json desactualizado", avisos[1])

    def test_limpio(self):
        self.assertEqual(sa.avisos_know({"sync": {"ok": True, "errores": []}, "flags": {}}), [])


class TestSecondClaude(Base):
    def preparar(self, log, cola=(), edad_sesion=0.0, pendientes=(), edad_pend=0.0):
        write(os.path.join(self.sc, "log.md"), log)
        staging = os.path.join(self.tmp, "staging")
        entradas = []
        for sid, nombre in cola:
            write(os.path.join(staging, "sesiones", nombre), "s", edad_sesion, self.ahora)
            entradas.append({"nombre": nombre, "sesion": sid, "titulo": "Asunto privado"})
        write(os.path.join(staging, "por_clasificar.json"), json.dumps(entradas))
        write(os.path.join(self.sc, "estado", "pendientes.json"), json.dumps(list(pendientes)),
              edad_pend, self.ahora)
        return staging

    def test_ingesta_reciente_sin_avisos(self):
        hoy = time.strftime("%Y-%m-%d %H:%M", time.localtime(self.ahora - 3600))
        staging = self.preparar(f"# Log\n\n## {hoy} — ingesta\n\n- ok\n")
        self.assertEqual(sa.revisar_second_claude(self.sc, staging, self.ahora, 2), [])

    def test_ingesta_vieja_y_entrada_manual_no_cuenta(self):
        viejo = time.strftime("%Y-%m-%d %H:%M", time.localtime(self.ahora - 5 * DIA))
        hoy = time.strftime("%Y-%m-%d %H:%M", time.localtime(self.ahora))
        staging = self.preparar(f"## {viejo} — ingesta\n\n## {hoy} — patrones (manual)\n")
        avisos = textos(sa.revisar_second_claude(self.sc, staging, self.ahora, 2))
        self.assertEqual(len(avisos), 1)
        self.assertIn(viejo, avisos[0])

    def test_sesion_parada_sin_titulo(self):
        hoy = time.strftime("%Y-%m-%d %H:%M", time.localtime(self.ahora))
        staging = self.preparar(f"## {hoy} — ingesta\n", cola=[("d2eb9d44-aaaa", "s_x1.md")],
                                edad_sesion=4)
        avisos = textos(sa.revisar_second_claude(self.sc, staging, self.ahora, 2))
        self.assertEqual(len(avisos), 1)
        self.assertIn("d2eb9d44", avisos[0])
        self.assertNotIn("Asunto privado", avisos[0])

    def test_pendientes_que_no_bajan(self):
        hoy = time.strftime("%Y-%m-%d %H:%M", time.localtime(self.ahora))
        staging = self.preparar(f"## {hoy} — ingesta\n", pendientes=[{"archivo": "a"}], edad_pend=3)
        avisos = textos(sa.revisar_second_claude(self.sc, staging, self.ahora, 2))
        self.assertEqual(len(avisos), 1)
        self.assertIn("sin integrar", avisos[0])


class TestWiki(Base):
    def test_enlaces(self):
        write(os.path.join(self.know, "2026-10-08 CIC api MDM EMS", "summary.md"))
        write(os.path.join(self.sc, "raw", "resumenes", "r.md"))
        write(os.path.join(self.sc, "index.md"), "Formato: `- [Titulo](ruta)`\n- [P](wiki/proyectos/p.md)\n")
        write(os.path.join(self.sc, "wiki", "proyectos", "p.md"),
              "- bien ([fuente](../../raw/resumenes/r.md))\n"
              "- know ([summary](../../../Know/2026-10-08%20CIC%20api%20MDM%20EMS/summary.md))\n"
              "- know <> ([summary](<../../../Know/2026-10-08 CIC api MDM EMS/summary.md#x>))\n"
              "- web [w](https://example.com) y ancla [a](#resumen)\n"
              "- roto ([fuente](../../raw/resumenes/no.md))\n"
              "```\n[ejemplo](no-existe.md)\n```\n")
        rotos = sa.enlaces_rotos(self.sc)
        self.assertEqual(rotos, [(os.path.join("wiki", "proyectos", "p.md"), "../../raw/resumenes/no.md")])
        self.assertEqual(len(textos(sa.revisar_wiki(self.sc))), 1)


if __name__ == "__main__":
    unittest.main(verbosity=1)
