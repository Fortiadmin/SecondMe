# Revisión de arquitectura Azure y CI/CD de la plataforma MDM/CEGEM con CIC — 17 de julio de 2026

**Fecha:** 2026-07-17 · **Duración:** 2:27:47 · **Fuente:** `2026-07-17 Revisión arquitectura Azure.mkv`
**Transcripción:** Parakeet TDT 0.6b v3 local (GPU), 754 segmentos, sin diarización
**Convocatoria:** "[Fortia][Sesion4] Infra +CI/CD", viernes 17/07/2026 a las 13:00, reunión de Teams con Rubén Aizcorbe Ocejo en el evento (`frames_1280/frame_0004.jpg`).
**Frames:** 42 en `frames_1280/` (1280 px). También hay 32 en `frames/` (512 px), que duplican a los anteriores.

> **La reunión ocupa 00:00–82:24 de la grabación.** De 82:24 a 2:27:47 no hay reunión. Se ve el escritorio, una pantalla bloqueada (14:31 del viernes 17 de julio, `frame_0037`), una pantalla en negro, el correo y VS Code.
> Los tiempos `MM:SS` son de la grabación. El contador de Teams va unos 1:42 por delante: el frame de 41:43 marca 43:25.
> La transcripción no identifica a quien habla. Los nombres salen de quien es nombrado en voz alta y de la galería de Teams. Lo marcado como *(inferido)* es deducción del contexto.

## Participantes

Diez personas en la reunión. La galería de Teams marca "Gente 10" hasta el minuto 62; desde ahí marca 8.

- **Fortia** *(afiliación inferida del contexto)*:
  - **Rafael Villacastin Sierra**, en cámara al principio.
  - **Álvaro Henriquez Juarez**, infraestructura Azure de Fortia: direccionamiento, management group y connectivity hub.
  - **Víctor García González**: MDC y Data Lake.
  - **Antonio Garcia Pereda**, quien graba. En 63:50 lo llaman "el experto de esto" (Git / CI/CD).
- **CIC (Consulting Informático), proveedor de la plataforma MDM/CEGEM** *(afiliación inferida)*:
  - **Roberto Hidalgo Cisneros** comparte y edita el diagrama. La transcripción dice "la flechita que ha puesto Robert" [~25:00] y "Roberto, tenía una pregunta…" [36:39].
  - **Jose Manuel Escobedo Garcia** ("José Escobedo"): dimensionamiento, coste, Envoy y, por contexto, la parte técnica del pipeline.
  - **Jose Luis Macho Merino** llega a las 00:38 junto con José Manuel Escobedo.
  - **Juan Jesús Peña Gómez** ("Juancho") hace de funcional.
  - **Francisco Marquijano Ruiz**: en la transcripción aparece un funcional "Marky/Marki/Marquis/Marquinhos". Que sea él es *inferido*, por el parecido del nombre.
  - **Rubén Aizcorbe Ocejo** inicia la transcripción de Teams, según el aviso en pantalla. En 00:00 alguien le pregunta si "hemos convocado nosotros y la podemos grabar".
- Hacia 61:55 dos personas dicen que tienen que irse. Desde ese momento la galería ya no muestra a Víctor García ni a Rubén Aizcorbe. Que fueran ellos quienes se fueron es *inferido*.

## Titular

Tercera o cuarta sesión de trabajo con CIC sobre la infraestructura y el CI/CD de la plataforma MDM/CEGEM en Azure. Hay una discrepancia de numeración, explicada en Cautelas.

En la primera hora CIC presenta la nueva versión del diagrama (`MDM_CEGEM_Arquitectura_Azure_15072026.drawio`) y del dimensionamiento del 15/07. El planteamiento es una suscripción dedicada, una VNet por entorno y un AKS con dos node pools, por unos 750 €/mes sin compromiso de permanencia. Se repasan una a una las integraciones: MDC (Axon Time), SIMEL (REE), Datadis, SFTP de distribuidoras, EMS y Data Lake.

Se acuerda:

- **un único Load Balancer**;
- que **todo el tráfico de entrada y salida pase por el connectivity hub de Fortia**, sin IP pública en la suscripción de la aplicación;
- que el **EMS se integre por API REST directa** y no a través del Data Lake;
- que el **Data Lake** se alcance por **endpoint privado**.

Álvaro arrancará el management group y la suscripción "este lunes" en cuanto CIC le pase los nombres y correos de sus técnicos.

Power BI se usará para los informes que proponía CIC, en lugar de "Luca". Los datos del MDM **no deben viajar al Data Lake**. Queda pendiente cómo conectar un workspace de Power BI directamente a la base de datos.

En la segunda parte CIC presenta el **Documento Técnico Integración CI/CD**:

- git flow reducido de tres ramas (main, pre, develop) con pull request y aprobación obligatoria;
- pipeline CI en Azure DevOps con build Java/Angular, test, SonarQube, Trivy, Docker, SBOM y ACR;
- despliegue en AKS automático en pre y con aprobación en PRO.

CIC completará el documento con el versionado y la calidad de código. Queda abierta la visibilidad del pipeline contra el SonarQube de Fortia.

## Temas tratados

### Arranque y orden del día — 00:00–01:18
- Se confirma que la reunión se puede grabar.
- CIC propone este orden: arquitectura, CI/CD y siguientes pasos. Dice que ya tiene "activado el equipo de infraestructuras que va a generar el despliegue" [00:19].
- Se quiere "aterrizar más operativamente": pedir que se despliegue la suscripción y pasar usuarios [00:42–00:56].
- CIC ha hecho una nueva versión de la arquitectura porque Rafael pidió afinar las integraciones con sistemas terceros, el Data Lake y Power BI [01:08–01:15].

### Red, suscripción y dimensionamiento — 01:18–04:55
- **Lo ya hablado** [01:31–02:21]:
  - Los usuarios de Fortia entran por el *connectivity hub* a través de la VPN, que está en otra suscripción.
  - La aplicación tendrá una **suscripción dedicada** con una **VNet por entorno**. La transcripción dice "una VNET para producción, una para pre y una para Pro", seguramente producción, pre y dev.
  - Álvaro ya pasó el direccionamiento y está incorporado [02:06].
  - Se usará **AKS** (Kubernetes gestionado) y varios servicios de Azure fuera del contenedor.
- **Dimensionamiento**: hay una nueva versión, "la de 15 del 7", con CPU, RAM y disco asignados a cada contenedor. Una hoja traduce eso a recursos para producción, pre y dev y para almacenamiento [02:36–03:28].
- **Coste estimado**: unos **750 € mensuales**, "sin ahorros, sin compromiso de permanencia" [03:45–04:00].
  - Lo calculó José Escobedo como primera aproximación y se volverá a afinar.
  - Según CIC entra en la estimación inicial.
- **Node pools** [04:08–04:47]:
  - Pool de sistema con 3 instancias. La transcripción dice "cuatro ASV5"; el diagrama, "3x Worker nodes D4as v5".
  - Pool de aplicación en **autoescalado de 2 a 5 nodos**, según la carga.

### Autoescalado — 04:55–07:06
- Alguien de Fortia pregunta si el escalado es instantáneo y si se cobra en el momento.
- CIC, José *(inferido)*, explica:
  - Por encima de un umbral de CPU y RAM que piden los pods, se aprovisiona un nodo nuevo, y así hasta cubrir la carga [05:09–05:29].
  - Está pensado sobre todo para los **procesos batch**, por ejemplo las recargas hacia las 12 de la noche. Al terminar se **desescala** y el nodo se elimina [05:29–05:48].
  - Los umbrales (p. ej. 80 %) son parametrizables y se fijarán cuando se vea la carga real [05:55–06:23].
- Rafael *(inferido: hablan de "nosotros vamos saltando de proyecto en proyecto")* pide que pongan en el chat **un enlace de Microsoft que explique el autoescalado** [06:28–07:02].

### Bloques funcionales dentro de AKS — 07:06–08:37
- **Pool de sistema**: pods de **observabilidad** y **servicios base de nodo**.
- **Pool de aplicación**:
  - pods de **base de datos**;
  - pods de **aplicación**: web, y APIs de notificaciones, inventario, medida, paramétricas y mejor valor, entre otras;
  - pods de **procesos batch**: cargas, cálculos y calidad. Son los que hacen que el sistema escale [07:22–08:37].
- Hay un bloque duplicado por error en el dibujo [08:19].
- El detalle del diagrama está en Capturas (`frame_0015`, `frame_0021`).

### Entrada de tráfico: Load Balancer y Envoy — 08:37–16:38
- CIC dibujó tres load balancers, uno por cada cara: usuarios, terceros ajenos a Fortia y otras plataformas de Fortia (EMS, Data Lake). Aclara que **en realidad es uno solo** y que se pintó así por claridad [09:42–10:20, 13:30–13:49].
- **Duda de CIC** [10:20–11:08]: los load balancers ¿cuelgan del entorno de la aplicación, o todo el tráfico pasa por el connectivity hub sin IP expuesta en la aplicación? Álvaro quiere saber cuánto tráfico llegará desde SIMEL y desde la izquierda del dibujo para valorar si hace falta un balanceador ahí [11:14–11:29].
- **Explicación de Envoy** (José Escobedo, *inferido*) [14:36–15:47]:
  - El Load Balancer de Azure balancea entre los nodos de AKS.
  - **Envoy** (Envoy Proxy y Envoy Gateway) recibe las peticiones y las reparte a los pods, haciendo de *ingress*.
  - Hay pods de Envoy en cada nodo.
- CIC reorganiza el dibujo en tres bloques: humano-máquina, máquina-máquina con terceros externos y otras plataformas de Fortia. Todo pasa por el load balancer y de ahí a Envoy [14:01–14:33, 16:08–16:20].

### Integraciones con terceros ajenos a Fortia — 11:45–36:38
CIC tenía apuntados MDC, SIMEL (REE), Datadis y, por indicación de los funcionales, los **SFTP de las distribuidoras** [11:51–12:08]. Álvaro necesita el protocolo, el sentido de la conexión y el tipo de tráfico de cada uno [12:13–12:26].

**MDC (Axon Time)** — 16:38–21:07
- "Pendiente de definir". Se sabe que es **por API HTTPS (443), no SFTP**.
- CIC no tiene la especificación. **Víctor la tiene y la enviará** [17:10–17:16].
- Es un servicio contratado que ya funciona y que usan otros clientes [17:30].
- El MDM consulta y trae información, así que la conexión es **saliente** [17:41–18:05].
- Se etiqueta la caja del MDC como "Axon Time" [19:18].
- Discusión sobre cómo pintar la flecha: el sentido funcional de la información es el contrario al de la conexión [20:22–20:37].

**Inventario desde el EMS (Fortia)** — 18:06–19:05
- Alguien de Fortia señala que falta en el dibujo la recepción **vía API** del inventario del EMS, de la que se habló la sesión anterior.
- Se añade abajo, con color distinto, como sistema de Fortia.

**SIMEL (REE)** — 21:12–~30:00
- **Es REE quien se conecta a nuestro sistema.** Hace falta un dominio y un certificado que proporciona REE, y el sistema tiene que ser accesible por REE [21:27–21:44].
- **Situación actual en Fortia** [21:57–23:54]:
  - Hay un pequeño desarrollo, "en Java o en una vaca", con el certificado.
  - Se usa la "Magic Folder" para descargar los ficheros a un buzón.
  - Las **reclamaciones** se suben **a mano** en la plataforma SIMEL. Fortia solo envía reclamaciones: "no somos concentrador secundario".
- **Funcionamiento en el sistema nuevo** (lo explica el funcional de CIC, *inferido* "Marky", que dice haber montado varios para comercializadoras) [22:47–24:12]:
  - REE llama **cada minuto** a un **web service que hay que construir**, preguntando si hay ficheros disponibles. Cuando el sistema marca un fichero para enviar, se lo entrega a REE. Por ahí irían las reclamaciones.
  - Para descargar, un **proceso de captación** se conecta a REE con un **certificado de cliente** y sustituye a la Magic Folder.
- **Certificados** [24:16–~27:00]:
  - El trámite lo gestiona la comercializadora ante una "ventanilla" de REE.
  - REE entrega un **certificado de cliente**, para descargar, y un **certificado de servidor**, para que REE recoja los ficheros.
  - Hacen falta **en PRE y en PRO**.
  - El certificado de servidor iría en el **Envoy Proxy**, que hace el *mutual TLS* y enruta al pod.
- **Homologación** [~27:00–~29:00]:
  - El web service está descrito en el **P1011**, con métodos cerrados.
  - REE exige un **test de pruebas**: se instala en PRE, se hacen las pruebas, REE da el OK y entrega los certificados y web services de PRO.
  - Son **cuatro web services**, uno por subsistema: peninsular, Baleares, Ceuta y Melilla, y Canarias. Fortia opera en peninsular y Canarias, pero REE pide los cuatro.
- **Contactos en REE**: se comenta que Ricardo Bajo "ya no" y que Emilio Barroso "tampoco". Hay que localizar a los nuevos.
- **Petición de Fortia** (sin atribución): CIC debe pasar la documentación concreta de REE para motivar bien la solicitud. La idea es citar el documento, la dirección de correo específica o el epígrafe del portal, y no hacerlo "de oídas". Alguien responde "me lo apunto, lo busco y se lo paso".
- **En 36:25 alguien pone en el chat el enlace a la documentación del protocolo de comunicaciones con REE**, que "tiene dibujos y está bastante claro".

**Datadis** — ~30:00
- Alguien de Fortia explica que es un sistema de las distribuidoras, por API HTTPS, pero que **va a desaparecer**, según lo oído en las reuniones de medidas.
- Para las medidas de distribuidora bastarían los SFTP, así que "a lo mejor no tiene sentido montarlo".
- No se decide en voz alta, pero en el diagrama revisado de 59:39 Datadis ya no aparece.

**SFTP de distribuidoras** — ~30:00–36:25
- **Funcionalmente solo hay descarga**: los SFTP de las distribuidoras importantes son de solo lectura y no se envían reclamaciones por ahí. Son los ficheros P1, P2…
- **Protocolos**: las grandes (Iberdrola, EDP) usan SFTP; la transcripción dice "FTP". Algunas pequeñas usan FTPS o FTP por el 21. **El robot de descargas tiene que soportar todos.**
- En el modelo de datos están definidos los servidores de cada grupo de distribuidoras, con direcciones y carpetas. El robot de descargas, que es el "batch de cargas", sabe adónde ir.
- **Es tráfico saliente**: sale por **Azure NAT Gateway**, con reglas de filtrado por IP de destino y puerto [~33:35–36:17].

### Seguridad: todo por el connectivity hub — 36:39–41:53
- **Pregunta de Fortia** (Álvaro, *inferido*) a Roberto [36:39–37:33]:
  - ¿Habrá una política de filtrado y de **monitorización del tráfico** por distribuidora y protocolo?
  - ¿Lo incluye el diagrama o lo tendría que montar Fortia con sus herramientas?
- Fortia ya analiza el tráfico en su connectivity hub "a través de Ben Hubs con CrossTrick". La lectura no es clara; ver Cautelas [38:00].
- **CIC (Roberto)**: la buena práctica es que el connectivity hub concentre conectividad y seguridad (WAF, firewalls, IPS). Lo lógico es que **no haya IPs públicas** en la aplicación y que todo entre por el hub y se enrute hacia dentro [38:32–39:57].
- **Fortia (infra)** [40:00–40:58]:
  - Hay que valorar poner un **WAF**. Ahora solo tienen uno, el de la aplicación web, y verán si lo adaptan o si ponen uno dedicado a la plataforma **CEGEM**.
  - Todo irá en un **management group distinto**, con **suscripción dedicada** y de forma aislada.
  - Solo estará unido al resto por el tenant y por las VNets (peering).
  - El objetivo es tener un canal central de entrada y salida de tráfico.
- **Decisión**: "Yo lo prefiero de esa manera, porque sería un poco más controlado" / "Es la manera canónica" / "Lo cambiamos así" [41:02–41:53].

### Sistemas internos de Fortia: EMS y Data Lake — 41:55–~49:00
*Tramo con varios segmentos que el reconocimiento convirtió al inglés (ver Cautelas).*
- **EMS**:
  - Está en un **hosting de AYESA**. El Data Lake, en la infraestructura Azure de Fortia [42:33–42:46].
  - Ya hay conectividad entre el EMS y el tenant de Azure, que se usa para alimentar el Data Lake. Se pregunta si se puede reutilizar [42:46–43:34].
  - Víctor plantea sacar del Data Lake la información del EMS, por ejemplo el inventario, porque las tablas del EMS ya se suben allí [44:08–44:32].
  - Se descarta: usar el Data Lake "como hub de comunicaciones" no gusta y **mete un día de retraso** por los pipelines [44:38–44:53].
- **Decisión: integración directa con el EMS** mediante **API REST**, "lo que estamos haciendo últimamente para no acceder a la base de datos". Pasará por el connectivity hub, porque el EMS está fuera de Azure [~45:00].
- **Anécdota**: alguien recomienda usar **Claude** para generar diagramas de draw.io. Dice que "hace seis meses era una castaña" y que ahora da dibujos "dignos" [~45:30].
- **Data Lake**:
  - Está en **otra suscripción**.
  - Se representará con un **endpoint privado**, no accesible desde internet.
  - Álvaro pasará a Roberto la **VNet donde está el recurso del Data Lake** por el **canal de Teams** del proyecto [~47:00–~48:30].

### Puesta en marcha en Azure — ~48:30–52:20
- **Región**: CIC pregunta si se definió **West Europe o Francia** y lo deja "a vuestra decisión". **No consta respuesta.**
- CIC pregunta qué necesita Álvaro para empezar.
- **Álvaro** [50:06–52:05]:
  - Hará el despliegue del **management group** "este lunes".
  - Creará el management group, **una suscripción** y, dentro, grupos de recursos. Dice "tres", pero luego habla de "producción y no producción"; ver Cautelas.
  - Necesita una **lista con nombres y correos** de las personas de CIC y de las tareas de cada una, para dar accesos y roles.
- CIC desplegará con script (**Terraform**, a cargo de José).
- Álvaro dará un rol de tipo "developer" en la suscripción. Si una aplicación pide **consentimiento en el tenant**, CIC debe avisar por Teams.

### Power BI — 52:20–61:40 (y 79:18–80:58)
- **Posición de Fortia** (Rafael, *inferido*):
  - CIC propuso unos informes con "**Luca**" que gustaron. Fortia pidió hacerlos en **Power BI** para tener una única plataforma de acceso a la información.
  - **No se quiere la base de datos del MDM entera en el Data Lake**: hay mucha medida no definitiva, con tratamiento, que al día siguiente se relee y cambia [52:41–53:44].
- Son **informes concretos, descritos en el funcional de la oferta**, no acceso a las tablas de medidas o inventario [55:51–56:10]. Víctor lo confirma [55:10–55:24].
- **CIC**:
  - Entendía el requisito como cuadros de mando.
  - Podría enseñar en la demo una propuesta dentro de la propia web.
  - Lo hablará con "Paz" [54:37–55:01].
  - Recuerda que Luca permitía atacar todo en conjunto. Sin Luca, hay que concretar qué informes se necesitan [55:25–55:51].
- **Arquitectura** [56:22–60:10]:
  - Los usuarios de Fortia entran por el túnel site-to-site (HTTPS) con el navegador a la web y también a Power BI.
  - Power BI ya está licenciado y desplegado en Fortia.
  - Lo que hace falta es **conectividad de Power BI a la base de datos**, "como el SSO pero en sentido contrario".
  - El informe es un fichero que se sube a Power BI con sus *data sources*.
- **Propuesta**: en el **workspace de informes** de Fortia, definir un **data source nuevo con conexión directa (SQL) a la base de datos de la plataforma**, sin que los datos pasen por el Data Lake. Hoy todos los informes de Fortia van contra el Data Lake. "Habría que verlo con ellos también" [60:32–61:36].
- **Al cierre** [79:21–80:58]:
  - Rafael *(inferido)* pregunta si Álvaro ha hablado con **Esther** sobre cómo montarlo.
  - Respuesta: los workspaces con pipeline se autentican de forma automática, que es lo que han trabajado la semana anterior. Habría que ver cómo conectar uno a la base de datos de CIC.
  - Álvaro "le dará una vuelta con Esther".
  - "La idea es que los datos no viajen al Data Lake… del MDM".

### Cambio de presentador — 61:40–64:24
- Se ha consumido el tiempo previsto. CIC tiene disponibilidad y sigue con el CI/CD.
- Dos personas se van: "Yo sí me tengo que salir" / "Yo también, Roberto, tengo otra hora".
- Problemas de audio y cambio de sala en CIC.
- Alguien pregunta si sigue Antonio, "que es el experto de esto" [63:46–63:52].

### Documento técnico de CI/CD — 64:24–77:17
CIC presenta el documento aparte que se acordó hacer: `F07.03.01.00.12.r02_Fortia_Doc_Tecnico_CICD.docx`, "Documento Técnico Integración CI/CD". Ver `frame_0022` y `frame_0024`. Según su introducción, la estrategia "se implementará en **Azure DevOps**", con enfoque **DevSecOps** y dos pipelines: **CI** y **Deploy sobre AKS**.

**Modelo de ramas** — 65:00–68:28
- **main**: despliegues a PRO.
- **pre**: entorno de preproducción. No pasa a PRO hasta superar las pruebas de negocio y técnicas.
- **develop**: integración de *features* y *fixes*.
- Se mantiene la rama pre para poder corregir un *hotfix* sin bloquear la versión que está en aceptación [65:35–66:05].
- Hoy los desarrolladores trabajan directamente sobre la rama. **Cuando estén la infraestructura y el CI/CD, todo irá por pull request con aprobación obligatoria** [66:39–67:16]. Es como trabajan "en casi todos los proyectos en CIC".
- Es "un git flow reducido", con normas de revisión, aprobaciones y etiquetado en los pases develop → pre → main [67:47–68:19].

**Pipeline CI** — 68:56–71:56
- Se toma como referencia lo que Fortia tiene "descrito en el script": en la fase de *code quality*, **SonarScanner CLI** publica contra **SonarQube** [69:08–69:33].
- El flujo se dispara tras el *merge*:
  1. **Build** de **Java** y **Angular**.
  2. **Test unitarios**.
  3. En paralelo, **SonarScanner → SonarQube** y escaneo de vulnerabilidades de librerías con **Trivy** (TrivyFS).
- Si se supera el **umbral crítico** que se fije, el pipeline se rechaza y hay que corregir [70:23].
- Al final del CI se publica un informe. Como hace Fortia, se crea un `README.md` / `sonarqube.md` con el enlace al resultado y se adjuntan los ficheros generados [70:54].
- Después:
  1. **Imagen Docker**, evaluada otra vez con **Trivy** (TrivyImage).
  2. **SBOM**.
  3. Publicación en **Azure Container Registry**.
  4. Los informes quedan asociados al pipeline [71:15–71:51].

**Despliegue (CD)** — 71:56–73:52
- Despliegue en **AKS**, validación y, si falla, **rollback** a la versión anterior.
- **Preproducción**: despliegue automático al terminar la publicación (*continuous deployment*).
- **Producción**: requiere **aprobación**, normalmente con un pull request sobre el repositorio de despliegue que actualiza la versión del microservicio [72:19–73:05].
- "Eso no lo hemos incorporado, pero lo agregamos en el documento" [73:52]. El tramo intermedio está mal segmentado y no queda claro a qué se refiere exactamente.

**Detalle de fases y versionado** — 74:10–75:11
- El documento detalla qué se ejecuta y qué resultado se espera en cada fase.
- En la generación del Docker hay una **propuesta de versionado**. CIC se adapta a lo que indique Fortia y **incluirá una política de versionado** en el documento.

**SonarQube** — 75:11–77:17
- Alguien de Fortia pregunta si "le mandaste a Antonio" la forma de conectarse a SonarQube y si han podido probar. José Manuel ("Manuel") busca el correo de Antonio.
- **Duda de CIC**: cómo tendrá **visibilidad el pipeline contra el servidor SonarQube** para publicar el informe [76:23–76:42].
- En el correo se ve la URL "TST MS Fuerte Energía" (probablemente el entorno TST del EMS de Fortia). La gestión de ese entorno "es de **Adrián**".

### Cierre y siguientes pasos — 77:17–82:20
- CIC rematará el documento CI/CD con el versionado y la calidad de código y lo enviará [77:22–77:33].
- CIC enviará el **dibujo de arquitectura afinado** y empezará a documentarlo mejor [77:51–78:13].
- CIC enviará **nombres y contactos de sus técnicos** para que Álvaro dé de alta suscripciones y accesos [78:13–78:27].
- CIC empezará con los **scripts de despliegue** [78:30–78:37].
- **Próxima reunión**: "para que no nos pase lo de esta semana", se propone el **miércoles a la una y media**. Otra opción fue el viernes a las 11:30. Alguien intentará reenviar o replicar la convocatoria [78:37–79:14].
- Power BI con Esther (ver arriba) [79:18–80:58].
- Despedida [82:18–82:20].

## Decisiones confirmadas

1. **Un único Load Balancer** de entrada. Los tres del dibujo eran representación. Detrás, **Envoy** reparte a los pods [13:30–13:49, 16:08].
2. **Todo el tráfico de entrada y salida pasará por el connectivity hub de Fortia** y no habrá IPs públicas en la suscripción de la aplicación. Lo prefiere infraestructura de Fortia (Álvaro, *inferido*) y CIC responde "Lo cambiamos así" [41:02–41:53]. Se refleja en el diagrama de 59:39.
3. **Plataforma aislada**: management group propio y suscripción dedicada, conectada al resto por tenant y VNet peering [40:12–40:52].
4. **Integración con el EMS por API REST directa**, no a través del Data Lake, porque el Data Lake mete un día de retraso. Pasa por el connectivity hub [44:38–~45:30].
5. **Data Lake por endpoint privado**, en su propia suscripción [~47:00].
6. **Sentido y protocolo de las integraciones** en el diagrama revisado:
   - MDC (Axon Time): HTTPS (API) saliente.
   - SIMEL (REE): HTTPS (API) entrante, con certificado de servidor de REE terminado en Envoy (mTLS).
   - SFTP de distribuidoras: saliente por Azure NAT Gateway y de solo lectura.
   - EMS: HTTPS (API).
   - Usuarios: VPN S2S y Entra Conditional Access.
7. **Power BI en lugar de Luca** para los informes descritos en el funcional de la oferta. **Los datos del MDM no van al Data Lake.** Es una posición de Fortia que nadie discute; *cómo* conectarlo sigue pendiente.
8. **Git**: tres ramas (main = PRO, pre, develop) con pull request y aprobación obligatoria una vez montado el CI/CD. CIC lo presentó y no hubo objeciones de Fortia ("Sí, sí, eso es").
9. **Despliegue**: automático en preproducción y con aprobación en producción [72:19–73:05].

## Propuestas (sin confirmar)

- **Autoescalado** del pool de aplicación de 2 a 5 nodos y umbrales tipo 80 %. Es estimación de CIC y se ajustará con la carga real.
- **Coste** de unos 750 €/mes sin compromiso. Primera aproximación, "volveremos a afinar".
- **No montar Datadis** porque va a desaparecer. Se plantea, no se decide, aunque ya no está en el diagrama revisado.
- **WAF** en el connectivity hub, adaptando el de la web o con uno dedicado a CEGEM. Fortia lo "valorará".
- **Power BI**: data source nuevo en el workspace de informes de Fortia con conexión SQL directa a la base de datos del MDM. Pendiente de verlo con Esther y con "ellos".
- **CIC**: enseñar en la demo una propuesta de cuadros de mando dentro de la propia web.
- **Pipeline CI** completo (Java/Angular, test, SonarQube, Trivy FS e imagen, SBOM, ACR) con rechazo por umbral crítico. Es el contenido del documento de CIC; los umbrales no están fijados.
- **Política de versionado** de imágenes: hay propuesta de CIC, pendiente de lo que indique Fortia.
- **Próxima sesión** el miércoles a las 13:30 (22/07/2026 si es la semana siguiente, *inferido*). No consta convocatoria enviada.

## Pendientes

| # | Pendiente | Responsable | Fecha / condición |
|---|---|---|---|
| 1 | Enviar el diagrama de arquitectura con los cambios acordados (connectivity hub, un LB, EMS, Data Lake por PE) y empezar a documentarlo | CIC (Roberto) | Sin fecha |
| 2 | Completar el documento CI/CD con versionado, calidad de código y aprobación de despliegue en PRO, y enviarlo | CIC | Sin fecha |
| 3 | Enviar nombres, correos y tareas de los técnicos de CIC para dar accesos y roles | CIC | Antes del despliegue del management group |
| 4 | Crear management group, suscripción y grupos de recursos (producción / no producción) y asignar roles | Álvaro Henriquez | "Este lunes" (20/07/2026, *inferido*) |
| 5 | Decidir la región: West Europe o Francia | Fortia (lo dejan "a vuestra decisión") | No consta |
| 6 | Pasar la VNet del recurso del Data Lake por el canal de Teams | Álvaro Henriquez | Sin fecha |
| 7 | Enviar la especificación de la API del MDC (Axon Time) | Víctor García | Sin fecha |
| 8 | Pasar la documentación de REE (P1011 / protocolo de comunicaciones) para pedir los certificados de cliente y servidor. Ya se puso un enlace en el chat en 36:25 | CIC (funcional, *inferido* "Marky") | Sin fecha |
| 9 | Pedir a REE los certificados (cliente y servidor, PRE y PRO) y localizar los contactos nuevos | Fortia (comercializadora) | Antes de las pruebas de homologación en PRE |
| 10 | Construir y homologar los cuatro web services SIMEL (peninsular, Baleares, Ceuta y Melilla, Canarias) | CIC | Pruebas en PRE y luego certificados de PRO |
| 11 | Resolver el filtrado y la monitorización del tráfico por distribuidora y protocolo en el hub; valorar el WAF | Fortia (infra) | Sin fecha |
| 12 | Ver cómo conectar un workspace de Power BI a la base de datos del MDM sin pasar por el Data Lake | Álvaro Henriquez con Esther | Sin fecha |
| 13 | Concretar con "Paz" el planteamiento de los informes y cuadros de mando | CIC | Sin fecha |
| 14 | Resolver la visibilidad del pipeline de CIC contra el SonarQube de Fortia (entorno gestionado por Adrián) | CIC / Fortia (Antonio) | Sin fecha. Ver `frame_0039`: permisos de administración ya concedidos a Antonio ese día |
| 15 | Poner en el chat un enlace de Microsoft sobre el autoescalado de AKS | CIC | Durante la reunión. No consta si se hizo |
| 16 | Convocar la siguiente sesión (miércoles 13:30) | No consta quién ("voy a ver si puedo reenviarla yo") | Semana siguiente |

## Capturas relevantes

- `frames_1280/frame_0004.jpg` (t=00:39): calendario de Outlook del 12 al 18 de julio. El viernes 17 a las 13:00 figura "[Fortia][Sesion4] Infra +CI/CD" con Rubén Aizcorbe Ocejo.
- `frames_1280/frame_0003.jpg` (t=00:05): la ventana de Teams se titula "[Fortia][**Sesion3**] Infra +CI/CD". Ver Cautelas.
- `frames_1280/frame_0015.jpg` (t=34:32): **diagrama inicial** `MDM_CEGEM_Arquitectura_Azure_15072026.drawio`.
  - Integraciones a la izquierda: MDC (Axon Time) saliente, SIMEL (REE) entrante, Datadis entrante, SFTPs por Azure NAT Gateway, EMS (Fortia).
  - Load Balancer Standard. Entorno PRO, VNet PRO, 1 región y 2 zonas de disponibilidad.
  - **Node pool Sistema**:
    - Observabilidad: Grafana, Alert Manager, Loki, Tempo, OpenTelemetry Collector, Prometheus, Prometheus Operator, Kube State Metrics, Node Exporter.
    - Servicios base de nodo: Cilium Agent, Envoy Proxy, Envoy Gateway Controller, CoreDNS, containerd, kubelet, Metrics Server, Cilium Operator.
    - 3x Worker nodes D4as v5.
  - **Node pool Aplicación**:
    - Web-SPA Angular.
    - API Notificaciones, Inventario, Medida, Paramétrica, Mejor Valor, Objeciones e I/O SIMEL.
    - CloudNative PG Operator, Primary y Replica.
  - Galería con nombres legibles.
- `frames_1280/frame_0019.jpg` (t=59:39): **diagrama revisado**. Arriba, MDC, SIMEL, SFTPs, usuarios de Fortia (navegador web y Power BI por VPN S2S + Entra Conditional Access) y EMS https(API) saliente. Todo cae en una franja de conectividad con NSG/ACL, VPN Gateway y Azure NAT Gateway, unida por **peering** al Entorno PRO con un **único Load Balancer Standard**. **Datadis ha desaparecido.**
- `frames_1280/frame_0021.jpg` (t=1:01:51): "Servicios gestionados de Azure (fuera de AKS)": Entra ID (req.) por OIDC/JWT, Blob Storage (ficheros+Backups) y Key Vault (req.) por HTTPS, y Managed Disks por CSI.
- `frames_1280/frame_0022.jpg` (t=1:02:49): portada e índice del "Documento Técnico Integración CI/CD" de CIC, `F07.03.01.00.12.r02_Fortia_Doc_Tecnico_CICD.docx`, marcado Confidencial.
- `frames_1280/frame_0024.jpg` (t=1:03:40): introducción del documento: Azure DevOps, DevSecOps, Pipeline CI y Pipeline Deploy sobre AKS, y objetivos. Índice con Stage Build, UnitTests (Integración con SonarQube), TrivyFS y CodeQuality.
- `frames_1280/frame_0025.jpg` (t=1:17:08): apartado 2.7 Stage TrivyImage (Alpine, Ubuntu, Debian, Red Hat UBI). Ventana flotante de Teams "[Fortia][Sesion4] Infra +CI/CD" con 8 personas.
- `frames_1280/frame_0033.jpg` (t=1:22:26), **ya sin reunión**: notas adhesivas de quien graba. "Tareas que tengo pendientes del proyecto CIC: Acceso a Repositorios de Código, Ubicación y Acceso a SonarQ, Ejemplo de Ejecución de Pipelines en Azure…" y "Sonarqube -> Pedirles correo a usuario Sonarqube". No es contenido de la reunión.
- `frames_1280/frame_0039.jpg` (t=2:26:00), **posterior a la reunión**: correo "usuario Sonarqube".
  - Antonio Garcia Pereda pidió a Adrian Garcia Alonso (Alten) el 17/07 a las 12:17 permisos de administración en SonarQube para asociar `cic-azure-devops`.
  - Adrian contesta a las 13:48: "Ya te los he dado".

## Cautelas de la transcripción

**Sobre la grabación**
- **Hay 65 minutos de grabación sin reunión.** La reunión acaba en 82:24 y la grabación sigue hasta 2:27:47. La duración real de la reunión es de unos 82 min, más los ~1:42 que no se grabaron al principio según el contador de Teams.
- **Numeración de la sesión.** La convocatoria del calendario y la ventana flotante de Teams dicen "[Fortia][Sesion4] Infra +CI/CD". La ventana principal de Teams dice "[Fortia][Sesion3] Infra +CI/CD". Al cierre alguien dice "para que no nos pase lo de esta semana", que *podría* ser una confusión de convocatoria. No se resuelve.

**Segmentación y reconocimiento**
- **Segmentos fusionados**: los bloques que empiezan en [25:00], [30:00] y [45:00] abarcan unos 5 minutos cada uno, sin marcas internas. Los tiempos marcados con "~" dentro de esos tramos son aproximados.
- **Cambio de idioma**: entre 40:00 y 45:00 el modelo tradujo frases al inglés ("Andrew systems internos", "The MS is a system that is in a hosting"). El sentido se reconstruye por contexto.
- **Nombres mal reconocidos (lectura probable)**:
  - Infraestructura y Azure:
    - "data leck / data link" = Data Lake
    - "Forti / Portia" = Fortia
    - "connectivity HAD" = connectivity hub
    - "VN / OVNET" = VNet
    - "KS / castellet / K7 y K4" = AKS
    - "no de pulse" = node pools
    - "cuatro ASV5" = D4as v5
    - "BATS" = batch
    - "envoyo / se los envoy" = Envoy
    - "Azure Enat / Night / Azulinad Gateway" = Azure NAT Gateway
    - "network pin" = private endpoint
  - Integraciones:
    - "MS" = EMS
    - "Simel / SEMEL / Smail / Sibel / Gmail / email" = SIMEL
    - "data dis / datadiza / data this" = Datadis
    - "X o N… Axon Time" = Axon Time
    - "SEGEM" = CEGEM
  - CI/CD:
    - "C y C D / CEI" = CI/CD, CI
    - "Fiat Ur" = feature
    - "hotel" = hotfix
    - "DBODA" = develop
    - "Trivi" = Trivy
    - "SBUM" = SBOM
    - "RITMI MD" = README.md
    - "sonar cube" = SonarQube
    - "The Terra for José" = Terraform
  - Otros:
    - "Power Bay / Power B" = Power BI
    - "Robert / ruberto" = Roberto
- **Sin lectura fiable**:
  - "Ben Hubs con CrossTrick" (herramienta de análisis del hub; ¿vHubs? ¿CrowdStrike?).
  - "Luca/Lucas" (herramienta de informes que propuso CIC).
  - "paz" (¿una persona de CIC llamada Paz?).
  - "portal pasos".
  - "Magic Folder / Magic Ford".
  - "Shimmer".
  - "TST MS Fuerte Energía" (URL del SonarQube).
  - "Mario" en 79:03: no hay ningún Mario entre los participantes.
  - **P1011** se deja tal cual; *podría* ser el procedimiento de operación 10.11 de REE (*inferido*).
- **"Marky / Marquinhos" = Francisco Marquijano** y **"Juancho" = Juan Jesús Peña** son inferencias por el parecido del nombre y por el contexto.

**Inconsistencias en lo dicho**
- **VNets y grupos de recursos**: CIC habla de una VNet por entorno ("producción, pre y Pro", seguramente dev, pre y pro). Álvaro dice "tres grupos de recursos" y luego "producción y no producción". No se aclara.
- **Load balancer**: en 09:10 se dice "balanceador de carga básico", pero el diagrama pone "Load Balancer Standard".
- **SFTP de distribuidoras**: la transcripción dice "FTP" para las grandes. Por el contexto (SFTP saliente en el diagrama) seguramente es SFTP.

**Frames que no son de la reunión**
- `frame_0006` (26:57) muestra en la pantalla de quien graba un ticket de Redmine (#27364, facturas de gas).
- `frame_0016`/`0017` (41:43–41:51) y `frame_0042`/`0043` muestran su VS Code (repositorio MCPServer_Redmine).

**Correcciones al resumen anterior** (escrito solo con los frames de 512 px, sin transcripción)
- Decía que la reunión no tenía transcripción ni informe y que la fuente era `audio.mp3`. Ahora hay `report.md` con 754 segmentos y la fuente original es el `.mkv`.
- Decía "seis recuadros de Teams con iniciales JG, RC, JG, JM, AJ, FR, sin nombres legibles". A 1280 px los nombres se leen: son nueve participantes remotos más quien graba. "RC" es Roberto Hidalgo Cisneros.
- La "ventana oscura con código o configuración y un panel de texto con una lista larga de puntos" superpuesta al diagrama **no era material de la reunión**: es el VS Code local de quien graba.
- La "paleta de formas de Azure ('Azure MIT Gateway', … Finance)" era la búsqueda "Azure NAT Gateway" de draw.io, sin resultados, y las categorías genéricas de formas.
- En el documento CI/CD **no hay ningún "plan de ejecución nocturno"**. El índice real es Arquitectura General / Modelo de trabajo GIT / Flujo CI/CD / Pipeline CI con stages Build, UnitTests, TrivyFS, CodeQuality y TrivyImage.
- El calendario que se tomó por "sin valor" contiene la convocatoria de la reunión (`frame_0004`).
- La relación con `2026-09-02 Seguimiento CIC`, que antes se daba por "no afirmable", queda ahora respaldada en el contenido: CIC es el proveedor de la plataforma MDM/CEGEM y aquí se acuerda el despliegue con Terraform sobre AKS que esa reunión sigue.

## Relación con otras carpetas

- **`2026-09-02 Seguimiento CIC`**: seguimiento del despliegue del entorno de desarrollo con Terraform sobre AKS en **France Central**, bloqueado por las zonas de disponibilidad de la talla de nodo. Aquí la región quedó abierta entre West Europe y Francia.
- **`2026-10-08 CIC api MDM EMS`**: workshop de gobierno del dato del MDM, donde vuelven a salir Axon Time, la API hacia el EMS y Power BI por DirectQuery contra el Postgre del MDM frente al Data Lake.
- Solo he leído la cabecera de esos resúmenes. Las dos relaciones conviene contrastarlas en sus fuentes antes de dar por hecha la evolución.
