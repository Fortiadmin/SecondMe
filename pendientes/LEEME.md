# Pendiente: rehacer el resumen de 2026-07-17 Revisión arquitectura Azure

El summary.md de esa carpeta de Know se escribió solo con frames, cuando no había
transcripción. El 2026-11-01 un agente redactó uno nuevo con la transcripción de
Parakeet (report.md, 754 segmentos) y los 42 frames de frames_1280, pero se dejó en
pausa antes de publicarlo. Know sigue con el resumen y el meta.json antiguos.

- `summary-2026-07-17-borrador.md`: resumen propuesto (revisar antes de publicar).
- `meta-2026-07-17-propuesto.json`: meta.json acorde a ese resumen (sin `fuentes`).

Para publicarlo: copiar ambos a la carpeta (como summary.md y meta.json), y luego
`python _kb/kb.py stamp "2026-07-17 Revisión arquitectura Azure"` y `python _kb/kb.py sync`
desde la raíz de Know.
