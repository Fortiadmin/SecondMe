# Fase 3: el wiki de Second Claude se alimenta también de las reuniones

Planteada el 2026-11-01. Estado a 2026-11-02:

- **Hecho:** la comprobación de salud (`salud/salud.py`, 12 tests), que se ejecuta en LauncherV y
  en el paso 7 de la tarea diaria.
- **Hecho:** el piloto a mano en `wiki/proyectos/mic96.md`, con 2 reuniones de Know y 8
  seguimientos de SecondB.
- **Hecho (automatización, aprobada el 2026-11-02):** `extraer.py reuniones` y
  `confirmar-reuniones` (con `estado/reuniones.json`, la huella sha1 del resumen y 2 tests
  nuevos), la sección «Reuniones» del `CLAUDE.md` de Second Claude y el paso 6b de la tarea diaria
  (tandas de 15, como mucho 3 por ejecución). La carga inicial, de 71 reuniones, empezó el
  2026-11-02 con una ejecución manual de la tarea:
  - 45 integradas (del 2026-07-17 al 2026-10-01), sin errores;
  - 6 páginas creadas y 21 actualizadas;
  - 3 contradicciones anotadas con la regla 7;
  - salud en orden.
  Las 26 restantes (del 2026-10-01 al 2026-10-30) entran en la ejecución diaria siguiente.
- **Pendiente de comprobar tras esa ejecución:** que la página `mdm-cic` recoja el workshop del
  2026-10-08 y que la búsqueda "Power BI sin pasar por el data lake" lo encuentre.
- **Observación:** el subagente tiende a añadir secciones «Ampliación AAAA-MM-DD» al final de la
  página en vez de repartir lo nuevo por las secciones del formato. Es el mismo patrón que ya
  tenía el wiki. Vigilarlo; si molesta, reforzar la regla en el `CLAUDE.md`.
- **Decisiones:** D1 descartada (no se mueven carpetas). D2, D3 y D4 aprobadas como se proponen
  abajo.

## Resultado del piloto (2026-11-02)

Misma pregunta ("¿Cómo ha evolucionado el asunto MIC96 y qué queda abierto?") a dos agentes
nuevos con la skill `cerebro`, uno antes y otro después.

| | Antes | Después |
|---|---|---|
| Coste | 11 llamadas, ~134 K tokens | 10 llamadas, ~142 K tokens |
| Plan de puesta en PRO (04/09, 18/09) | no aparece | aparece, con el fallo de rondas intermedias conocido antes de subir |
| Acuerdo del 29/10 con OMIE (robot graba en tablas EMS) | no aparece | aparece |
| Efectos en la forma de trabajar (estado «Aceptada», pruebas del cambio de hora) | parcial | completo |
| Pendientes y contradicciones de tickets | buenos | buenos, casi iguales |
| #27772 (pérdidas de BC por las 96 rondas) | aparece | no aparece |

Lectura: mejora la historia (lo anterior a la subida y lo más reciente), pero no ahorra tokens ni
llamadas, porque el agente sigue leyendo SecondB. MIC96 era el proyecto mejor cubierto por
sesiones; en uno con pocas sesiones la diferencia debería ser mayor (sin comprobar).

## Qué era la fase 3 en el plan original

1. El paso de integración de Second Claude lee también las reuniones, para que una página de
   proyecto (MIC96, BC, Entra ID, MDM-CIC…) junte sesiones de Claude y reuniones.
2. Juntar las dos copias de `trans-reunion` en una. **Hecho** el 2026-11-01: solo queda
   `~/.claude/skills/trans-reunion`.
3. Mover las carpetas a una raíz común. **Propongo descartarlo** (ver decisión D1).

Y la comprobación de salud diaria, que era transversal y sigue sin hacer. Propongo meterla aquí
como primer paso (ver decisión D4).

## Cómo funciona hoy (comprobado el 2026-11-01)

- Tarea programada `second-claude-ingesta`, diaria a las 09:04
  (`~/.claude/scheduled-tasks/second-claude-ingesta/SKILL.md`, 31 líneas).
- Paso 5: lee `estado/pendientes.json` (sesiones aceptadas y sin integrar), toma sus resúmenes
  de `raw/resumenes` y, en tandas de unos 30 ordenadas por fecha, lanza un subagente Opus con
  esfuerzo bajo que crea o amplía páginas en `wiki/` e `index.md`. Paso 6:
  `extraer.py confirmar` saca de pendientes lo integrado.
- Wiki: 18 proyectos, 29 temas y 16 entidades. Cada afirmación enlaza su fuente
  `raw/resumenes/…` (regla 4 de su `CLAUDE.md`).
- Ya hay tres páginas que mencionan Know o SecondB: `know-reuniones`, `ems-soporte-seguimiento`
  y `mic96`, pero porque se habló de ellas en sesiones, no porque se lean las reuniones.
- Fuentes de reuniones: 52 en Know (`summary.md` + `meta.json`) y 21 páginas en
  `SecondB/Control Servicio EMS/memoria/reuniones/` (más `_plantilla.md`).

## Diseño propuesto

**Qué se lee.** Solo lo consolidado: `summary.md` de Know (no `report.md` ni transcripciones) y
las páginas de `memoria/reuniones` de SecondB. Así no entra nada que no haya pasado ya por un
resumen, y el coste es bajo.

**Nada se copia a `raw/`.** La reunión ya vive en su cerebro. Copiarla duplicaría conocimiento y
rompería los borrados, que es justo lo que prohíbe el `CLAUDE.md` de Know. El wiki enlaza la
fuente original con ruta relativa:
- Know: `../../../Cajon/Know/<carpeta>/summary.md`
- SecondB: `../../../SecondB/Control Servicio EMS/memoria/reuniones/<fecha>-EMS.md`

**Qué pendiente se lleva.** Nuevo estado `estado/reuniones.json` en Second Claude, con la ruta y
la huella (tamaño + mtime, o hash) de cada resumen ya integrado. Un comando nuevo,
`extraer.py reuniones`, lista lo nuevo o cambiado. `extraer.py confirmar-reuniones <rutas>`
lo marca como integrado. Se calcula al vuelo y no hace falta tocar Know ni SecondB.

**Quién lo integra.** El mismo paso 5 de la tarea, con un párrafo más en las instrucciones del
subagente:
- Una reunión de Know aporta a la página de proyecto, tema o entidad con decisiones, problemas,
  pendientes y conocimiento, y su porqué. Se cita con `(reunión AAAA-MM-DD, [fuente](…))`.
- Un seguimiento de SecondB **no** se vuelca ticket a ticket: eso ya lo tiene SecondB con su
  estado de acuerdos. Al wiki solo pasa lo que cambia el conocimiento de un proyecto o tema, con
  un enlace a la página del ticket en SecondB.
- Las reglas de Second Claude siguen igual: contradicción → `> Cambio AAAA-MM-DD…` (regla 7),
  fechas absolutas y nada de secretos. Lo que se lee pasa antes por los patrones de
  `extraer.py`.
- Sin diarización: la reunión no dice quién habló, así que el wiki no atribuye frases.

**Carga inicial.** Las 73 reuniones de una vez, por orden de fecha, en tandas de 30 (3 tandas).
Leer los resúmenes son unos 650 K caracteres (514 K de Know y 138 K de SecondB, ≈ 185 K tokens) más las páginas del wiki que toque,
con Opus en esfuerzo bajo como hoy. Después, unas pocas reuniones por semana dentro de la tarea
diaria.

**Índice único.** No cambia nada: `cerebro.py` ya indexa el wiki, y las páginas ampliadas se
reindexan solas por la firma.

## Decisiones que te toca tomar mañana

- **D1. Mover las carpetas a una raíz común: DESCARTADO** (aprobado el 2026-11-02). El índice único ya
  da la vista conjunta sin moverlas. Moverlas obligaría a cambiar rutas fijas en tres skills, la
  tarea programada, `cerebro.py`, `ingesta_videos.py` y los `CLAUDE.md`, y el de Know prohíbe
  mover carpetas. Además, OneDrive sincronizaría de nuevo varios GB.
- **D2. Enlaces fuera del wiki.** Si abres Second Claude como bóveda de Obsidian, un enlace a
  `../../../Cajon/Know/…` sale de la bóveda y Obsidian no lo sigue (VS Code sí). Opciones:
  a) aceptarlo; b) abrir como bóveda la carpeta raíz de OneDrive; c) citar la reunión por su id
  del índice (`know:2026-10-08 CIC api MDM EMS`) en vez de por ruta.
- **D3. ¿Entran también los seguimientos de SecondB, o solo Know?** Propongo que entren, con la
  regla de no volcar tickets. Si prefieres empezar pequeño, solo Know.
- **D4. Comprobación de salud.** Propongo hacerla antes que la integración: es determinista, sin
  modelo, y protege también lo que ya existe. ¿Al arrancar LauncherV, en la tarea diaria o en
  las dos?

## Pasos (si se aprueba como está)

1. **Salud** (`SecondMe/salud/salud.py`, solo biblioteca estándar, sin modelo). Comprueba:
   - vídeos de `C:\V` sin tratar desde hace más de 2 días; elementos en la bandeja o en
     `revisar` desde hace más de 2 días;
   - Know: `kb.py status` sin errores y sin `meta-desactualizado`;
   - Second Claude: última entrada de `log.md` de hace menos de 2 días, staging retenido por
     secretos, `pendientes.json` sin crecer de forma indefinida;
   - SecondB: reuniones publicadas sin `ingesta-<id>.json` (sin consolidar);
   - `cerebro.py status` y enlaces rotos del wiki (incluidos los nuevos a Know y SecondB).

   Salida: una línea por aviso y código de salida distinto de 0 si hay alguno. Con tests.
2. `extraer.py reuniones` y `confirmar-reuniones` + `estado/reuniones.json`, con tests junto a
   los 8 actuales de `test_extraer.py`.
3. Ampliar el `CLAUDE.md` de Second Claude: fuente "reuniones", formato de cita y regla de los
   seguimientos.
4. Ampliar el paso 5 de la tarea programada (`SKILL.md`): tras las sesiones, integra las
   reuniones pendientes.
5. Carga inicial a mano, en esta sesión o en una nueva, con 3 tandas. Revisar 3 o 4 páginas
   (MIC96, BC, MDM-CIC, cambio de hora) antes de dejarla en la tarea diaria.
6. README de SecondMe y nota en `log.md` de Second Claude.

## Criterio de éxito

- La página `mic96` cita a la vez sesiones de Claude y las reuniones de Know (informe a Dirección
  12/10, análisis de problemas) con enlaces que abren.
- La pregunta "Power BI conectado directamente a Postgres del MDM" encuentra una página del wiki
  `mdm-cic` que lo dice con la cita del workshop del 08/10.
- Una segunda ejecución sin reuniones nuevas no integra nada ni gasta tokens en ello.
- `salud.py` detecta, en una prueba, un vídeo viejo sin tratar y un enlace roto.

## Riesgos

- **Contaminación del wiki.** Un resumen de reunión con un error pasa al wiki y se cita como
  hecho. Mitigación: el wiki siempre enlaza la fuente, y la regla 7 deja rastro de los cambios.
- **Duplicación.** El wiki repite lo que ya está en Know o SecondB. Se acepta solo como síntesis
  con enlace, nunca como copia, y los enlaces rotos los detecta la comprobación de salud cuando
  se retira o se borra una reunión.
- **La tarea diaria crece.** Con una carga inicial a mano, el coste diario sigue siendo de unas
  pocas reuniones.
