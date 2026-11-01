# SecondMe — ingesta y consulta de los segundos cerebros

Dos piezas:

- **`ingesta/`** lleva las grabaciones de `C:\V` a Know y a SecondB (LauncherV y la skill `ingesta-v`).
- **`cerebro/`** es el índice único de los tres cerebros (Know, SecondB y Second Claude), con la skill
  `cerebro` para preguntarles. Se describe en la sección [Índice único](#índice-único-cerebro).

## Ingesta de grabaciones

Lleva las grabaciones de `C:\V` a los dos cerebros:

- **Seguimientos del servicio** (EMS y Axapta con el proveedor) → memoria del servicio,
  `OneDrive\SecondB\Control Servicio EMS\reuniones\<fecha>-<EMS|Axapta>\`, con `trans-reunion`.
- **Todo lo demás** → `OneDrive\Cajon\Know\<fecha> <título>\`, con `consolida-reuniones`.

Se lanza a mano con el icono **LauncherV** del escritorio (`LauncherV.bat`). No hay tareas
programadas.

## Flujo

```
C:\V\*.mkv
   │  1. ingesta\ingesta_videos.py procesar      (sin modelo; un vídeo cada vez, prioridad baja)
   ▼     /watch una sola vez: Parakeet local, frames por escena + frames dirigidos, audio Opus
C:\V\.ingesta\bandeja\<elemento>\   report.md · frames\ · audio.ogg · video.json
   │  2. Claude, skill /ingesta-v               (un elemento cada vez)
   │     a. convocatoria de Teams en el calendario de Outlook (solape con la grabación)
   │     b. revisión de frames: hojas de contacto → quitar / añadir
   │     c. publicar → destino según enrutado.json
   ▼     d. consolida-reuniones (Know) o trans-reunion (SecondB)
Know\<fecha> <título>\                       report.md · frames\ · audio.ogg · convocatoria.json
SecondB\...\reuniones\<fecha>-<sistema>\     transcripcion-<id>.md · frames-<id>\t-MMSS.jpg · audio.ogg
```

Mientras procesa, LauncherV muestra una línea de avance por vídeo: fase de `watch`, porcentaje,
tiempo transcurrido y estimado, y avance total con el tiempo que queda. Es una **estimación**: la
duración del vídeo por la velocidad aprendida de los anteriores (unos 0,16 s de proceso por
segundo de grabación en este portátil, guardada en `estado.json`). Se queda en 99 % hasta que el
vídeo termina de verdad.

Antes de abrir Claude, LauncherV **sugiere modelo y esfuerzo** (`sugerencia`, reglas fijas, sin
gastar tokens) y ofrece abrirlo con ellos (S), con tu configuración por defecto (P) o no abrirlo (N):

| Qué hay que hacer | Sugerencia | Por qué |
|---|---|---|
| Algún seguimiento del servicio (SecondB) | Opus, esfuerzo `high` | `trans-reunion` coteja tickets, compromisos e identidades entre reuniones; un error contamina la memoria |
| Solo reuniones para Know | Sonnet, esfuerzo `high` | resumen, metadatos, convocatoria y revisión de frames |
| Nada en la bandeja ni por consolidar | no abrir Claude | — |

Nunca sugiere `xhigh` ni `max`: no aportan a esta tarea y multiplican el razonamiento. Un elemento
con nombre de solo fecha y hora puede resultar un seguimiento al ver la convocatoria; si se abrió
con Sonnet, lo procesa con Sonnet (avisa de cuántos hay así).

El paso 1 es determinista y no llama a ningún modelo. Todo lo que mueve o edita ficheros, también
en el paso 2, lo hace el script; Claude solo decide.

## Comandos

```bash
python ingesta/ingesta_videos.py inventario [--todos]
python ingesta/ingesta_videos.py procesar [--max N] [--desde YYYY-MM-DD] [--solo "<video>"]
python ingesta/ingesta_videos.py bandeja [--json]
python ingesta/ingesta_videos.py hojas "<elemento>"
python ingesta/ingesta_videos.py frames "<elemento>" --quitar a.jpg,b.jpg --anadir "12:30 motivo"
python ingesta/ingesta_videos.py publicar "<elemento>" [--convocatoria F] [--asunto S] [--titulo T]
python ingesta/ingesta_videos.py revisar "<elemento>" "<motivo>"
python ingesta/ingesta_videos.py pendientes [--json]
python ingesta/ingesta_videos.py ignorar "<video>"...
```

Estados de `inventario`:

| Estado | Qué significa |
|---|---|
| `pendiente` | por procesar |
| `grabando` | modificado hace menos de 10 min |
| `descartado` | menos de 1 MB (grabación vacía) |
| `fallido` | 3 intentos fallidos; el motivo se ve en `inventario` |
| `sin-audio` | la pista de audio es silencio (pico ≤ −60 dB, OBS sin fuentes de audio): no hay nada que transcribir y no se reintenta |
| `ignorado` | marcado con `ignorar` |
| `en-bandeja` / `revisar` | procesado, a la espera de `/ingesta-v` o de una decisión tuya |
| `publicado` | ya en su cerebro, sin consolidar |
| `borrable` | consolidado (Know: resumen + `meta.json`; SecondB: `ingesta-<id>.json` + página en `memoria/reuniones`). **El vídeo se puede borrar a mano** |

Un vídeo cuenta como tratado si algún `.md` de la bandeja, de Know o de SecondB cita su nombre
de fichero en una línea `Source:`/`Fuente:`/`Origen:`/`Grabación:`. El estado local
(`C:\V\.ingesta\estado.json`) solo guarda fallos, ignorados y apartados: se puede borrar sin que
nada se reprocese. Log: `C:\V\.ingesta\ingesta.log`.

## Enrutado (`ingesta/enrutado.json`)

Manda el nombre del fichero (`Seg EMS`, `Seg Alten`, `Seg Axapta`); si no dice nada, el **asunto
exacto** de la convocatoria (`Seguimiento desarrollos Alten - Fortia` → EMS, `Seguimiento AXAPTA`
→ Axapta). Ni "seguimiento" ni la presencia de Alten bastan por sí solos: hay reuniones con Alten
que no son el seguimiento ("Pruebas de API BC->EMS") y seguimientos que no son del servicio
("Seguimiento ejecutivo PKF Business Central").

Título en Know: el del nombre del fichero si lo tiene; si es solo fecha y hora, el asunto de la
convocatoria; sin convocatoria, uno deducido del contenido. Nunca se pisa una carpeta existente.

## Decisiones

- **Una sola transcripción por vídeo**, local con Parakeet. Si `watch` devuelve otra cosa, se para:
  el audio de las reuniones no sale de la máquina.
- **Audio Opus mono a 32 kbps** (unos 12 MB/h) junto a la reunión: cuando el vídeo se borre, sigue
  siendo posible diarizar o volver a transcribir. No se publica ni el `.mp3` ni el `.wav` de `watch`.
- **Los frames se revisan en la bandeja**, mientras el vídeo existe: después ya no se pueden sacar
  frames nuevos. La revisión quita también lo ajeno a la reunión que se cuela en pantalla
  (notificaciones, avisos de seguridad, notas del escritorio).
- **Bandeja y trabajo en `C:\V\.ingesta`**, fuera de OneDrive y fuera de `%LOCALAPPDATA%`, que el
  Python de la Microsoft Store virtualiza.

## Pruebas

```bash
python ingesta/test_ingesta_videos.py
```

30 pruebas sobre carpetas temporales con un `/watch` falso; no tocan `C:\V`, Know ni SecondB.

## Índice único (cerebro)

`cerebro/cerebro.py` lee **sin modificarlos** los tres cerebros y los indexa juntos en
`cerebro/indice.db` (SQLite FTS5 con BM25; derivado, fuera de OneDrive y fuera de git). Solo usa
biblioteca estándar y no llama a ningún modelo.

| Cerebro | Qué se indexa | Fichas |
|---|---|---|
| Know | `summary.md` + `meta.json` de cada reunión (no `_retiradas` ni `_kb`) | reunión, documento |
| SecondB | `memoria/reuniones/*.md`; tickets (página + `historial_tickets.csv` + `acuerdos.csv` con su estado); `temas.csv` agregado por tema | seguimiento, ticket, tema |
| Second Claude | `raw/resumenes/*.md` (sin los "descartar") y `wiki/*/*.md` | sesion, wiki-proyecto, wiki-tema, wiki-entidad |

Cada documento es una **ficha** con el mismo esquema: cerebro, tipo, fecha, título, personas, tickets,
claves, texto, ruta y detalle. Sus secciones de decisiones, pendientes, acciones, problemas,
conocimiento, propuestas y compromisos se trocean en **átomos** (cada punto de lista o fila de tabla),
que se indexan aparte. Así una búsqueda devuelve la frase exacta y la ficha a la que pertenece. Las
secciones de cautelas, capturas y lecturas no se indexan.

```bash
python cerebro/cerebro.py search "función de reparto del continuo" [--cerebro …] [--tipo …] [--desde …] [--hasta …]
python cerebro/cerebro.py ticket 27703          # lo que dicen los tres cerebros, en orden
python cerebro/cerebro.py show "know:2026-10-28 Seg Business Central"
python cerebro/cerebro.py grep "Intermoney" --ambito transcripciones   # literal, con [MM:SS] / [~MM:SS]
python cerebro/cerebro.py status
python cerebro/cerebro.py sync                  # forzar la reconstrucción (normalmente no hace falta)
```

**Ranking.** Primero va lo que cubre más términos de la consulta **en un mismo átomo**, o en el
título y las claves de la ficha. Después cuenta BM25, que pondera más el título que las claves y las
claves más que el texto. La fecha solo desempata: un acuerdo antiguo no caduca por ser antiguo. El
texto corrido de una ficha no cuenta para la cobertura, porque un resumen largo "cubriría" cualquier
consulta. Los alias son los de `Know/_kb/aliases.json`, también los de varias palabras.

**Frescura.** Cada consulta compara una firma de las fuentes (número de ficheros y última
modificación) con la del índice, y si ha cambiado lo reconstruye antes de responder. Con unas 430
fichas y 3.000 átomos tarda menos de un segundo.

**Skill `cerebro`.** Vive en `.claude/skills/cerebro/` y está enlazada con una unión de directorio
en `~/.claude/skills/cerebro`, así que sirve desde cualquier proyecto. Primero busca con varias
formulaciones, luego tira de `ticket`, `show` y `grep`, y para el estado actual va a las fuentes vivas
(AgenteRed, Microsoft 365). Cita siempre cerebro, fecha y fuente.

**Pendiente (fase 2b).** El átomo de "preguntas con las que se buscaría", generado con modelo, se
dejó para más adelante. Se añadirá si en uso real hay preguntas que no encuentran su respuesta
porque la respuesta está escrita con otras palabras.

Pruebas: `python cerebro/test_cerebro.py` (13, con tres cerebros de juguete en carpetas temporales).
