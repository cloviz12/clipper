# CLIPPER

Clips de streamers en tiempo real: detecta el momento, lo edita como Short (subtítulos animados, hook,
encuadre por caras, zooms, sacudidas, destellos y efectos de sonido) y lo publica en YouTube Shorts,
TikTok e Instagram Reels. Se maneja entre dos (o más) personas desde un panel web.

```
web/        Panel (Next.js) → se despliega en Vercel
worker/     Motor (Python) → corre solo, sin ventanas, en un PC o en un servidor (Docker)
supabase/   Base de datos, archivos y tiempo real (una migración)
```

## Cómo funciona

**En vivo (tiempo real).** El motor revisa cada 30 s los canales de la pestaña *En vivo*. Cuando uno
prende directo:

1. Graba solo los últimos 6 minutos en pedacitos de ~4 s (buffer circular, nunca el directo completo).
2. Escucha el chat (Twitch por IRC anónimo, Kick por su websocket, YouTube por su chat en vivo) y
   mide el volumen del audio segundo a segundo.
3. Aprende lo que es "normal" en ese directo y, cuando el chat (KEKW, JAJA, "clip", ???) y/o el audio
   se disparan, corta ~70 % antes del pico y ~30 % después (la reacción), y lo manda a editar.
4. En Twitch, además, toma al instante los clips nuevos que la gente va creando.

La sensibilidad se ajusta por canal en el panel (0.5 = más clips, 2 = solo picos enormes).

**Pedidos.** Un link de video, VOD o canal. Busca los picos sin bajar el video: la curva de "lo más
visto" de YouTube, el chat del directo, los subtítulos y, como último recurso, solo el audio en baja
calidad. Después baja en Full HD únicamente esos tramos.

**Edición (cada clip).**
- Whisper transcribe palabra por palabra (con el nombre del canal y el título del directo como pista).
- Quita el arranque muerto (si nadie habla al inicio).
- La IA (Claude, opcional) decide si el clip se entiende solo, le pone puntaje, escribe el hook en
  pantalla (verdadero y que el clip paga), el título de Shorts con palabras que se buscan, captions
  distintos para TikTok e Instagram, 4-5 hashtags, y corrige nombres mal escritos en los subtítulos.
- Encuadre: si hay facecam pequeña → cámara arriba + juego abajo; si la cámara es grande → recorte
  9:16 que sigue la cara; si no hay caras → video completo sobre fondo desenfocado.
- Efectos de cámara en los golpes (pico del chat, picos de audio, palabras fuertes): zoom de golpe,
  sacudida y destello, más un zoom de entrada.
- Efectos de sonido: whoosh de entrada, pop con el hook, impacto/glitch en cada golpe, riser antes del
  momento y cierre. El motor fabrica los suyos (sin derechos de por medio) y usa primero los que suban
  en la pestaña *Sonidos*, rotándolos para que no suenen iguales.
- Subtítulos animados (palabra activa resaltada, palabras fuertes más grandes y con color de acento),
  máximo 2 líneas, dentro de la zona segura; la letra y los colores cambian de clip a clip.
- Audio normalizado a -14 LUFS, H.264 1080×1920.

**Publicación.** Cada canal puede ir en *avisarnos para aprobar* (llega al panel con sonido y
notificación; "Publicar ya" en un toque) o *automático* (publica solo si la IA le da el puntaje mínimo
de Ajustes). También se puede programar a una hora.

## Puesta en marcha

### 1. Supabase
Crear un proyecto y correr la migración `supabase/migrations/20261118000000_inicio.sql`
(con la CLI: `supabase link` + `supabase db push`, o pegándola en el SQL Editor).
En *Authentication → Providers → Email* dejar activo el registro con correo.

### 2. Panel en Vercel
Importar el repo con **Root Directory = `web`** y poner las variables de `web/.env.example`.
La primera cuenta que se cree en el panel queda como dueña; desde *Equipo* se agrega el correo del
compañero y él se registra con ese correo.

URLs de regreso para las apps de las redes (cambiar por el dominio real):
- Google Cloud (YouTube Data API v3, cliente web): `https://DOMINIO/api/oauth/youtube/callback`
- TikTok for Developers (Login Kit + Content Posting API): `https://DOMINIO/api/oauth/tiktok/callback`
- Meta (Instagram API con inicio de sesión de Instagram): `https://DOMINIO/api/oauth/instagram/callback`

Luego en el panel, pestaña *Cuentas*, botón **Conectar** en cada red.

### 3. Motor
Copiar `worker/.env.example` como `worker/.env` y llenarlo (la `SUPABASE_SERVICE_ROLE_KEY` es secreta:
solo va aquí y en Vercel).

- **En Windows:** doble clic una sola vez a `worker/INSTALAR_EN_WINDOWS.bat`. Instala todo y deja el
  motor corriendo en segundo plano, sin ventanas, y arrancando solo cada vez que se prende el PC.
  `ACTUALIZAR_EN_WINDOWS.bat` lo reinicia con la última versión.
- **En un servidor:** `docker build -t clipper-motor worker && docker run -d --restart=always --env-file worker/.env -v clipper:/datos clipper-motor`.
  YouTube suele bloquear descargas desde servidores; para YouTube conviene el motor en un PC de casa.

Pueden correr varios motores a la vez (uno en el PC y otro en un servidor): se reparten los pedidos
sin repetirse. El estado de cada motor se ve arriba a la derecha del panel.

## Límites que hay que saber
- **YouTube:** los videos subidos por la API desde una app sin auditar quedan privados hasta que Google
  apruebe la app.
- **TikTok:** sin la auditoría de TikTok solo se publica privado; por eso el modo por defecto es
  *borrador* (llega a la bandeja de la app para publicarlo con un toque).
- **Supabase gratis:** 1 GB de archivos. El motor borra los videos ya publicados o descartados después
  de los días que digan los Ajustes (3 por defecto).
- Resubir clips de otros creadores puede traer reclamos de derechos: lo más seguro es trabajar con
  streamers que lo permitan o que tengan programa de clippers. Cada publicación lleva el crédito y el
  enlace al original.
