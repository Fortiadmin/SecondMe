#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pruebas de ingesta_videos.py. SOLO trabajan sobre carpetas temporales.

No ejecutan /watch ni ffmpeg: un watch falso escribe report.md y frames, y la
extraccion de frames dirigidos y de audio se sustituye por funciones que crean
ficheros de relleno. No tocan C:\\V, Know ni SecondB.

    python ingesta/test_ingesta_videos.py
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
import ingesta_videos as iv  # noqa: E402


def write(path, text, mode="w"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, mode, encoding=None if "b" in mode else "utf-8") as fh:
        fh.write(text)


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


REPORT = """# watch: video report

- **Source:** {src}
- **Duration:** 05:00 (300.0s)
- **Transcript:** 4 segments (via parakeet-tdt (local))

## Frames

Frames live at: `{work}\\frames`

- `{work}\\frames\\frame_0001.jpg` (t=00:00, reason=first-frame)
- `{work}\\frames\\frame_0002.jpg` (t=02:00, reason=scene-change)

## Transcript

_Source: parakeet-tdt (local)._

```
[00:05] Buenos dias a todos.
[00:40] El ticket 27661 sigue igual.
[02:10] Mira esta columna de la tabla.
[04:00] Pues nada, hasta el jueves.
```
"""

FAKE_WATCH = r'''
import os, sys
args = sys.argv[1:]
video = args[0]
work = args[args.index("--out-dir") + 1]
if "transcript" not in args:
    os.makedirs(os.path.join(work, "frames"), exist_ok=True)
    for n in ("frame_0001.jpg", "frame_0002.jpg"):
        open(os.path.join(work, "frames", n), "wb").write(b"x")
open(os.path.join(work, "audio.parakeet.wav"), "wb").write(b"x" * 10)
tpl = open(os.environ["FAKE_REPORT"], encoding="utf-8").read()
open(os.path.join(work, "report.md"), "w", encoding="utf-8").write(
    tpl.replace("{src}", video).replace("{work}", work))
'''

REGLAS = {
    "secondb_por_nombre": {r"\bseg(uimiento)?\.? ?ems\b": "EMS",
                           r"\bseg(uimiento)?\.? ?axapta\b": "Axapta"},
    "secondb_por_asunto": {"Seguimiento desarrollos Alten - Fortia": "EMS",
                           "Seguimiento AXAPTA": "Axapta"},
}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ingesta-test-")
        self.origen = os.path.join(self.tmp, "V")
        self.know = os.path.join(self.tmp, "Know")
        self.secondb = os.path.join(self.tmp, "SecondB")
        for d in (self.origen, self.know, os.path.join(self.secondb, "reuniones"),
                  os.path.join(self.secondb, "memoria", "reuniones")):
            os.makedirs(d)
        self._local = iv.LOCAL
        iv.LOCAL = os.path.join(self.tmp, "local")
        self._enrutado = iv.ENRUTADO
        iv.ENRUTADO = os.path.join(self.tmp, "enrutado.json")
        write(iv.ENRUTADO, json.dumps(REGLAS))
        self.watch = os.path.join(self.tmp, "fake_watch.py")
        write(self.watch, FAKE_WATCH)
        self.tpl = os.path.join(self.tmp, "report.tpl")
        write(self.tpl, REPORT)
        os.environ["FAKE_REPORT"] = self.tpl

    def tearDown(self):
        iv.LOCAL = self._local
        iv.ENRUTADO = self._enrutado
        shutil.rmtree(self.tmp, ignore_errors=True)

    def video(self, nombre, size=iv.MIN_BYTES + 1, edad_min=60):
        p = os.path.join(self.origen, nombre)
        with open(p, "wb") as fh:
            fh.truncate(size)
        t = time.time() - edad_min * 60
        os.utime(p, (t, t))
        return p

    def estados(self):
        return {os.path.basename(v): e
                for v, e, _ in iv.inventario(self.origen, self.know, self.secondb)}

    def relleno(self, video, t, destino):
        write(destino, b"x", "wb")
        return True

    def relleno_audio(self, video, destino):
        write(destino, b"x", "wb")
        return True

    def a_bandeja(self, nombre):
        return iv.procesar_video(self.video(nombre), self.watch, self.relleno,
                                 self.relleno_audio, volumen=lambda p: -12.0)

    def publicar(self, elemento, **kw):
        return iv.publicar(elemento, know=self.know, secondb=self.secondb, **kw)


class TestInventario(Base):
    def test_publicado_si_un_report_de_know_cita_el_video(self):
        self.video("2026-09-10 Reunion.mkv")
        write(os.path.join(self.know, "2026-09-10 Reunion", "report.md"),
              "# watch\n\n- **Source:** C:\\V\\2026-09-10 Reunion.mkv\n")
        self.assertEqual(self.estados()["2026-09-10 Reunion.mkv"], "publicado")

    def test_borrable_cuando_know_tiene_resumen_y_meta(self):
        self.video("2026-09-10 Reunion.mkv")
        d = os.path.join(self.know, "2026-09-10 Reunion")
        write(os.path.join(d, "report.md"), "- **Source:** C:\\V\\2026-09-10 Reunion.mkv\n")
        write(os.path.join(d, "summary.md"), "# R\n")
        write(os.path.join(d, "meta.json"), "{}")
        self.assertEqual(self.estados()["2026-09-10 Reunion.mkv"], "borrable")

    def test_secondb_borrable_solo_con_ingesta_y_pagina_en_memoria(self):
        self.video("2026-10-05 Seg EMS.mkv")
        d = os.path.join(self.secondb, "reuniones", "2026-10-05-EMS")
        write(os.path.join(d, "transcripcion-2026-10-05-EMS.md"),
              "# T\nFuente: 2026-10-05 Seg EMS.mkv · 19:17 · parakeet\n")
        self.assertEqual(self.estados()["2026-10-05 Seg EMS.mkv"], "publicado")
        write(os.path.join(d, "ingesta-2026-10-05-EMS.json"), "{}")
        self.assertEqual(self.estados()["2026-10-05 Seg EMS.mkv"], "publicado")
        write(os.path.join(self.secondb, "memoria", "reuniones", "2026-10-05-EMS.md"), "x")
        self.assertEqual(self.estados()["2026-10-05 Seg EMS.mkv"], "borrable")

    def test_cita_tolera_acentos_mayusculas_y_dobles_espacios(self):
        self.video("2026-09-24  proyectos paralelos.mkv")
        write(os.path.join(self.know, "x", "report.md"),
              "- **Source:** C:/V/2026-09-24 Proyectos Paralelos.mkv\n")
        self.assertEqual(self.estados()["2026-09-24  proyectos paralelos.mkv"], "publicado")

    def test_mismo_dia_otra_reunion_no_cuenta(self):
        self.video("2026-10-26 Seg EMS.mkv")
        write(os.path.join(self.know, "2026-10-26 datons", "report.md"),
              "- **Source:** C:\\V\\2026-10-26 datons Desarrollo IA framework.mkv\n")
        self.assertEqual(self.estados()["2026-10-26 Seg EMS.mkv"], "pendiente")

    def test_pequeno_descartado_y_reciente_grabando(self):
        self.video("2026-10-30 13-37-30.mkv", size=47_000)
        self.video("2026-11-01 10-00-00.mkv", edad_min=2)
        e = self.estados()
        self.assertEqual(e["2026-10-30 13-37-30.mkv"], "descartado")
        self.assertEqual(e["2026-11-01 10-00-00.mkv"], "grabando")

    def test_ignorado_y_fallido(self):
        self.video("a.mkv")
        self.video("b.mkv")
        iv.guardar_estado({"ignorados": ["a.mkv"],
                           "videos": {"b.mkv": {"intentos": iv.MAX_INTENTOS}}})
        e = self.estados()
        self.assertEqual(e["a.mkv"], "ignorado")
        self.assertEqual(e["b.mkv"], "fallido")

    def test_nombre_sin_fecha_toma_la_del_fichero(self):
        p = self.video("Pruebas II API BC.mp4")
        fecha = time.strftime("%Y-%m-%d", time.localtime(os.path.getmtime(p)))
        self.assertEqual(iv.nombre_elemento(p), f"{fecha} Pruebas II API BC")
        self.assertEqual(iv.nombre_elemento(self.video("2026-07-10  Pkf.mkv")), "2026-07-10 Pkf")


class TestCues(unittest.TestCase):
    def test_lineas_y_frames_del_report(self):
        rep = REPORT.replace("{src}", "v.mkv").replace("{work}", "W")
        self.assertEqual(iv.tiempos_de_frames(rep), [0, 120])
        self.assertEqual([t for t, _ in iv.lineas_transcripcion(rep)], [5, 40, 130, 240])

    def test_solo_cues_sin_frame_cercano(self):
        lineas = [(5, "Buenos dias"), (40, "El ticket 27661 sigue igual"),
                  (50, "y el 27700 tambien"), (130, "Mira esta columna")]
        # 40 es cue; 50 queda a menos de 20 s de 40; 130 a 10 s del frame de 120.
        self.assertEqual([t for t, _ in iv.elegir_cues(lineas, [0, 120])], [40])

    def test_anadir_cues_antes_de_la_transcripcion(self):
        rep = REPORT.replace("{src}", "v.mkv").replace("{work}", "W")
        out = iv.anadir_cues(rep, [(40, "W\\frames\\cue_00040.jpg", "El ticket `27661`")])
        self.assertLess(out.index("cue_00040"), out.index("## Transcript"))
        self.assertIn("(t=00:40, reason=cue: El ticket '27661')", out)
        self.assertEqual(iv.tiempos_de_frames(out), [0, 120, 40])


class TestAvance(unittest.TestCase):
    def test_fase_de_watch_toma_la_ultima(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "watch.log")
            write(p, "[watch] using local file\n[watch] extracting scene-aware frames\n")
            self.assertEqual(iv.fase_de_watch(p), "frames por escena")
            write(p, "[watch] extracting audio\n[watch] Parakeet TDT: transcribing...\n", "a")
            self.assertEqual(iv.fase_de_watch(p), "transcribiendo")
            self.assertEqual(iv.fase_de_watch(os.path.join(d, "no")), "preparando")

    def test_linea_con_porcentaje_del_video_y_del_total(self):
        av = iv.Avance([600.0, 1800.0], 0.16, io.StringIO())
        av.empezar(1)
        # 600 s de video x 0.16 = 96 s estimados; a los 48 s, mitad del video
        self.assertEqual(av.linea("transcribiendo", 48),
                         "  [1/2] [##########----------] 50% · transcribiendo · 00:48 de ~01:36"
                         " · total 12%, quedan ~5 min")
        self.assertIn(" 99% ", av.linea("transcribiendo", 500))   # nunca 100 antes de acabar
        av.terminar()
        av.empezar(2)
        self.assertIn("total 25%", av.linea("preparando", 0))

    def test_sin_duracion_solo_fase_y_tiempo(self):
        av = iv.Avance([None], 0.16, io.StringIO())
        av.empezar(1)
        self.assertEqual(av.linea("transcribiendo", 75), "  [1/1] transcribiendo · 01:15")

    def test_fuera_de_consola_no_escribe(self):
        buf = io.StringIO()
        av = iv.Avance([600.0], 0.16, buf)
        av.empezar(1)
        av("transcribiendo")
        av.terminar()
        self.assertEqual(buf.getvalue(), "")


class TestSugerencia(unittest.TestCase):
    def b(self, el, destino=None, titulo="", revisar=None):
        return {"elemento": el, "destino_por_nombre": destino,
                "titulo_de_fichero": titulo, "revisar": revisar}

    def test_nada_que_hacer(self):
        self.assertEqual(iv.sugerir([], [])["modelo"], "ninguno")
        self.assertEqual(iv.sugerir([self.b("x", revisar="dos convocatorias")], [])["modelo"],
                         "ninguno")

    def test_solo_know_sonnet(self):
        s = iv.sugerir([self.b("2026-10-15 Reunion tec Forflex", titulo="Reunion tec Forflex"),
                        self.b("2026-10-16 10-05-38")], [{"destino": "know", "carpeta": "K\\a"}])
        self.assertEqual((s["modelo"], s["esfuerzo"], s["elementos"]), ("sonnet", "high", 3))
        self.assertEqual(s["dudosos"], ["2026-10-16 10-05-38"])

    def test_algun_seguimiento_opus(self):
        s = iv.sugerir([self.b("2026-10-26 Seg EMS", "EMS", "Seg EMS")], [])
        self.assertEqual((s["modelo"], s["esfuerzo"]), ("opus", "high"))
        s = iv.sugerir([], [{"destino": "secondb", "carpeta": "R\\2026-10-29-EMS"}])
        self.assertEqual((s["modelo"], s["secondb"]), ("opus", ["2026-10-29-EMS"]))


class TestEnrutado(unittest.TestCase):
    def test_manda_el_nombre_y_luego_el_asunto_exacto(self):
        self.assertEqual(iv.enrutar("2026-10-29 Seg EMS", None, REGLAS), ("secondb", "EMS"))
        self.assertEqual(iv.enrutar("2026-08-31 Seguimiento Axapta", None, REGLAS),
                         ("secondb", "Axapta"))
        self.assertEqual(iv.enrutar("2026-10-29 10-34-00", "Seguimiento desarrollos ALTEN - Fortia",
                                    REGLAS), ("secondb", "EMS"))

    def test_seguimiento_o_alten_sueltos_no_bastan(self):
        for asunto in ("Seguimiento ejecutivo PKF Business Central",
                       "Reunión seguimiento contrato Atos-FORTIA", "Pruebas de API BC->EMS"):
            self.assertEqual(iv.enrutar("2026-10-30 12-10-43", asunto, REGLAS), ("know", None))
        self.assertEqual(iv.enrutar("2026-09-30 Migracion Axapta a BC", None, REGLAS),
                         ("know", None))

    def test_titulo_de_fichero(self):
        self.assertEqual(iv.titulo_de_fichero("2026-10-16 10-05-38"), "")
        self.assertEqual(iv.titulo_de_fichero("2026-10-30 Seg BC sin frames"), "Seg BC")
        self.assertEqual(iv.titulo_de_fichero("2026-10-15 Reunion tec Forflex"),
                         "Reunion tec Forflex")

    def test_limpiar_nombre(self):
        self.assertEqual(iv.limpiar_nombre("2026-10-30 Pruebas de API BC->EMS "),
                         "2026-10-30 Pruebas de API BC- EMS")
        self.assertEqual(iv.limpiar_nombre("a: b/c?."), "a b c")


class TestProcesar(Base):
    def test_deja_en_la_bandeja_report_frames_audio_y_ventana(self):
        el = self.a_bandeja("2026-10-30 13-10-06.mkv")
        self.assertEqual(el, os.path.join(iv.bandeja_dir(), "2026-10-30 13-10-06"))
        self.assertEqual(sorted(os.listdir(el)), ["audio.ogg", "frames", "report.md", "video.json"])
        self.assertEqual(sorted(os.listdir(os.path.join(el, "frames"))),
                         ["cue_00040.jpg", "frame_0001.jpg", "frame_0002.jpg"])
        rep = read(os.path.join(el, "report.md"))
        self.assertIn(os.path.join(el, "frames", "cue_00040.jpg"), rep)
        self.assertNotIn(os.path.join(iv.LOCAL, "trabajo"), rep)
        info = json.loads(read(os.path.join(el, "video.json")))
        self.assertTrue(info["inicio_local"].startswith("2026-10-30T13:10:06"))
        self.assertTrue(info["fin_local"].startswith("2026-10-30T13:15:06"))
        self.assertTrue(info["inicio_utc"].endswith("Z"))
        self.assertFalse(os.path.exists(os.path.join(iv.LOCAL, "trabajo", "2026-10-30 13-10-06")))
        self.assertEqual(self.estados()["2026-10-30 13-10-06.mkv"], "en-bandeja")

    def test_reescribe_la_ruta_que_declara_watch_aunque_sea_otra(self):
        write(self.tpl, REPORT.replace("{work}", "C:\\Virtual\\trabajo\\x"))
        el = self.a_bandeja("2026-10-30 y.mkv")
        rep = read(os.path.join(el, "report.md"))
        self.assertNotIn("Virtual", rep)
        self.assertIn(os.path.join(el, "frames") + "\\frame_0002.jpg", rep)

    def test_sin_frames_no_pide_cues(self):
        llamadas = []
        iv.procesar_video(self.video("2026-10-30 Seg BC sin frames.mkv"), self.watch,
                          lambda *a: llamadas.append(a) or True, self.relleno_audio,
                          volumen=lambda p: -12.0)
        self.assertEqual(llamadas, [])

    def test_transcripcion_que_no_es_parakeet_se_rechaza(self):
        write(self.tpl, REPORT.replace("parakeet-tdt (local)", "whisper (groq)"))
        with self.assertRaises(RuntimeError):
            self.a_bandeja("2026-10-30 x.mkv")
        self.assertFalse(os.path.exists(os.path.join(iv.bandeja_dir(), "2026-10-30 x")))

    def test_grabacion_muda_no_es_fallo_ni_se_reintenta(self):
        write(self.tpl, REPORT.replace("4 segments (via parakeet-tdt (local))", "none available"))
        v = self.video("2026-10-16 10-31-02.mkv")
        with self.assertRaises(iv.SinAudio):
            iv.procesar_video(v, self.watch, self.relleno, self.relleno_audio,
                              volumen=lambda p: -91.0)
        # con sonido y sin transcripcion es un fallo de Parakeet, no "no es Parakeet"
        with self.assertRaisesRegex(RuntimeError, "Parakeet no devolvio"):
            iv.procesar_video(v, self.watch, self.relleno, self.relleno_audio,
                              volumen=lambda p: -12.0)
        iv.guardar_estado({"videos": {"2026-10-16 10-31-02.mkv": {"sin_audio": True}}})
        self.assertEqual(self.estados()["2026-10-16 10-31-02.mkv"], "sin-audio")

    def test_audio_mudo_se_descarta_antes_de_watch(self):
        write(self.watch, "raise SystemExit('watch no deberia ejecutarse')\n")
        with self.assertRaises(iv.SinAudio):
            iv.procesar_video(self.video("2026-10-14 11-04-57.mkv"), self.watch, self.relleno,
                              self.relleno_audio, volumen=lambda p: -91.0)
        self.assertFalse(os.path.exists(os.path.join(iv.LOCAL, "trabajo", "2026-10-14 11-04-57")))

    def test_limpiar_trabajo(self):
        self.video("2026-10-30 roto.mkv")
        self.video("2026-10-16 mudo.mkv")
        for n in ("2026-10-30 roto", "2026-10-16 mudo", "2026-10-16 borrado", "2026-10-30 nuevo"):
            os.makedirs(os.path.join(iv.LOCAL, "trabajo", n))
        estado = {"videos": {"2026-10-30 roto.mkv": {"intentos": 1, "error": "x"},
                             "2026-10-16 mudo.mkv": {"sin_audio": True, "intentos": 1}}}
        borradas = iv.limpiar_trabajo(self.origen, estado)
        self.assertEqual(sorted(borradas), ["2026-10-16 borrado", "2026-10-16 mudo",
                                            "2026-10-30 nuevo"])
        self.assertEqual(os.listdir(os.path.join(iv.LOCAL, "trabajo")), ["2026-10-30 roto"])

    def test_fallo_cuenta_intentos_y_no_publica(self):
        self.video("2026-10-30 roto.mkv")
        write(self.watch, "import sys; sys.exit(3)\n")
        args = ["--origen", self.origen, "--know", self.know, "--secondb", self.secondb,
                "--watch", self.watch, "procesar"]
        with contextlib.redirect_stdout(io.StringIO()):
            for _ in range(iv.MAX_INTENTOS):
                self.assertEqual(iv.main(args), 1)
            self.assertEqual(iv.main(args), 0)      # ya no se reintenta
        self.assertEqual(self.estados()["2026-10-30 roto.mkv"], "fallido")


class TestPublicar(Base):
    def test_know_con_titulo_de_la_convocatoria(self):
        self.a_bandeja("2026-10-30 13-10-06.mkv")
        conv = {"asunto": "Reunión día 25 horas", "invitados": ["a@x.es"]}
        res = self.publicar("2026-10-30 13-10-06", convocatoria=conv)
        final = os.path.join(self.know, "2026-10-30 Reunión día 25 horas")
        self.assertEqual(res, {"destino": "know", "sistema": None, "carpeta": final})
        self.assertEqual(sorted(os.listdir(final)),
                         ["audio.ogg", "convocatoria.json", "frames", "report.md"])
        rep = read(os.path.join(final, "report.md"))
        self.assertIn(os.path.join(final, "frames", "cue_00040.jpg"), rep)
        self.assertNotIn(iv.bandeja_dir(), rep)
        self.assertFalse(os.path.exists(os.path.join(iv.bandeja_dir(), "2026-10-30 13-10-06")))
        self.assertEqual(self.estados()["2026-10-30 13-10-06.mkv"], "publicado")

    def test_know_el_titulo_del_fichero_manda_y_no_pisa(self):
        self.a_bandeja("2026-10-15 Reunion tec Forflex.mkv")
        write(os.path.join(self.know, "2026-10-15 Reunion tec Forflex", "notas.md"), "a mano")
        res = self.publicar("2026-10-15 Reunion tec Forflex", asunto="Otra cosa")
        self.assertEqual(os.path.basename(res["carpeta"]), "2026-10-15 Reunion tec Forflex (2)")
        self.assertEqual(os.listdir(os.path.join(self.know, "2026-10-15 Reunion tec Forflex")),
                         ["notas.md"])

    def test_know_sin_titulo_se_niega(self):
        self.a_bandeja("2026-10-16 10-05-38.mkv")
        with self.assertRaises(RuntimeError):
            self.publicar("2026-10-16 10-05-38")
        res = self.publicar("2026-10-16 10-05-38", titulo="Prueba de carga BC")
        self.assertEqual(os.path.basename(res["carpeta"]), "2026-10-16 Prueba de carga BC")

    def test_secondb_con_nombres_de_trans_reunion(self):
        self.a_bandeja("2026-10-29 10-34-00.mkv")
        res = self.publicar("2026-10-29 10-34-00",
                            asunto="Seguimiento desarrollos Alten - Fortia")
        final = os.path.join(self.secondb, "reuniones", "2026-10-29-EMS")
        self.assertEqual(res, {"destino": "secondb", "sistema": "EMS", "carpeta": final})
        self.assertEqual(sorted(os.listdir(final)), ["audio.ogg", "frames-2026-10-29-EMS",
                                                     "transcripcion-2026-10-29-EMS.md"])
        self.assertEqual(sorted(os.listdir(os.path.join(final, "frames-2026-10-29-EMS"))),
                         ["t-0000.jpg", "t-0040.jpg", "t-0200.jpg"])
        rep = read(os.path.join(final, "transcripcion-2026-10-29-EMS.md"))
        self.assertIn(os.path.join(final, "frames-2026-10-29-EMS", "t-0040.jpg") + "` (t=00:40", rep)
        self.assertNotIn("frame_0001", rep)
        # y el inventario la ve publicada (sigue citando el video) y pendiente de ingerir
        self.assertEqual(self.estados()["2026-10-29 10-34-00.mkv"], "publicado")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            iv.main(["--know", self.know, "--secondb", self.secondb, "pendientes", "--json"])
        self.assertEqual(json.loads(buf.getvalue()), [{"destino": "secondb", "carpeta": final}])

    def test_secondb_dos_el_mismo_dia_no_se_pisan(self):
        os.makedirs(os.path.join(self.secondb, "reuniones", "2026-10-29-EMS"))
        self.a_bandeja("2026-10-29 Seg EMS.mkv")
        with self.assertRaises(RuntimeError):
            self.publicar("2026-10-29 Seg EMS")
        self.assertTrue(os.path.isdir(os.path.join(iv.bandeja_dir(), "2026-10-29 Seg EMS")))

    def test_quitar_y_anadir_frames_antes_de_publicar(self):
        el = self.a_bandeja("2026-10-30 13-10-06.mkv")
        res = iv.editar_frames("2026-10-30 13-10-06", ["frame_0001.jpg", "cue_00040.jpg"],
                               [(185, "se ensena la tabla")], self.relleno)
        self.assertEqual(res, {"quitados": 2, "anadidos": 1, "quedan": 2})
        self.assertEqual(sorted(os.listdir(os.path.join(el, "frames"))),
                         ["extra_00185.jpg", "frame_0002.jpg"])
        rep = read(os.path.join(el, "report.md"))
        self.assertNotIn("frame_0001", rep)
        self.assertIn("extra_00185.jpg` (t=03:05, reason=manual: se ensena la tabla)", rep)
        with self.assertRaises(RuntimeError):
            iv.editar_frames("2026-10-30 13-10-06", ["no_existe.jpg"], [], self.relleno)
        res = self.publicar("2026-10-30 13-10-06", titulo="Dia 25 horas")
        self.assertEqual(sorted(os.listdir(os.path.join(res["carpeta"], "frames"))),
                         ["extra_00185.jpg", "frame_0002.jpg"])

    def test_anadir_sin_video_se_niega(self):
        self.a_bandeja("2026-10-30 z.mkv")
        os.remove(os.path.join(self.origen, "2026-10-30 z.mkv"))
        with self.assertRaises(RuntimeError):
            iv.editar_frames("2026-10-30 z", [], [(10, "x")], self.relleno)

    def test_hojas_de_contacto(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("sin Pillow")
        el = self.a_bandeja("2026-10-30 h.mkv")
        for n in os.listdir(os.path.join(el, "frames")):
            Image.new("RGB", (64, 36), "red").save(os.path.join(el, "frames", n), "JPEG")
        rutas = iv.hojas("2026-10-30 h")
        self.assertEqual([os.path.basename(r) for r in rutas], ["hoja-01.jpg"])
        res = self.publicar("2026-10-30 h", titulo="H")
        self.assertNotIn(".hojas", os.listdir(res["carpeta"]))

    def test_revisar_aparta_y_publicar_lo_limpia(self):
        self.a_bandeja("2026-10-16 10-52-53.mkv")
        with contextlib.redirect_stdout(io.StringIO()):
            iv.main(["revisar", "2026-10-16 10-52-53", "cubre dos convocatorias"])
        self.assertEqual(self.estados()["2026-10-16 10-52-53.mkv"], "revisar")
        self.publicar("2026-10-16 10-52-53", titulo="BC y Atos")
        self.assertEqual(iv.cargar_estado()["revisar"], {})

    def test_pendientes_know(self):
        write(os.path.join(self.know, "2026-10-30 a", "report.md"), "x")
        write(os.path.join(self.know, "2026-10-30 b", "report.md"), "x")
        write(os.path.join(self.know, "2026-10-30 b", "summary.md"), "x")
        write(os.path.join(self.know, "_kb", "report.md"), "x")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            iv.main(["--know", self.know, "--secondb", self.secondb, "pendientes", "--json"])
        self.assertEqual([o["carpeta"] for o in json.loads(buf.getvalue())],
                         [os.path.join(self.know, "2026-10-30 a")])


if __name__ == "__main__":
    unittest.main()
