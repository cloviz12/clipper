# CLIPPER

App de escritorio (Windows) para sacar clips de streamers en tiempo real. Detecta el momento, lo
edita como Short y lo publica en YouTube Shorts, TikTok e Instagram Reels. La edición incluye
subtítulos animados, hook, encuadre por caras, zooms, sacudidas, destellos y efectos de sonido.

Cada persona del equipo instala la app en su PC. Las dos apps comparten los mismos clips, canales y
ajustes a través de Supabase, así que cualquiera puede aprobar o publicar desde su computadora.

```
app/        App de escritorio: ventana + bandeja + servidor local + instalador
ui/         Pantallas de la app (Next.js exportado como archivos estáticos)
worker/     Motor: vigila directos, edita y publica (va dentro de la app; también corre en Docker)
supabase/   Base de datos compartida (migraciones)
.github/    GitHub construye el instalador solo y lo publica en Releases
```

## Instalar

1. En GitHub ve a **Releases** y descarga `CLIPPER-Setup-x.y.z.exe`. El compañero tiene que estar
   agregado como colaborador del repo para poder verlo.
2. Instálalo. No pide administrador y trae ffmpeg, el descargador y todo lo demás adentro.
3. La primera vez la app pide los datos de **Esta PC**: la URL y las llaves de Supabase (obligatorias)
   y, si quieren, las llaves de Claude, Google y TikTok. Esos datos se guardan solo en esa computadora.
4. Crea tu cuenta. La primera cuenta queda como dueña; desde **Equipo** agrega el correo del compañero.

Al cerrar la ventana, CLIPPER sigue en la bandeja (junto al reloj) vigilando y publicando. Para salir
del todo se usa el menú de la bandeja. En *Esta PC* se puede dejar que abra solo al prender el PC.

**Dos PCs a la vez:** cada canal en vivo lo vigila una sola PC. Si esa se apaga, la otra lo toma en
menos de 2 minutos. Los pedidos y las publicaciones también se reparten sin repetirse.

## Actualizaciones automáticas

Cada vez que se mergea algo a `main`, GitHub construye el instalador, lo prueba y lo publica en
**Releases** como versión `1.0.N`. Las apps instaladas revisan cada 30 minutos; si hay versión nueva la
bajan y la instalan en silencio cuando no hay ningún clip editándose, y vuelven a abrir solas en la
bandeja.

Como el repo es privado, la app necesita un token de GitHub de solo lectura para ver las versiones.
Se pega una sola vez en *Esta PC → Actualizaciones* y queda guardado en Supabase para las dos PCs.
Para crearlo: GitHub → Settings → Developer settings → **Fine-grained tokens** → *Generate new token* →
*Only select repositories: clipper* → permiso **Contents: Read-only**.

Cada PR también construye el instalador y lo deja como *artifact*, para probarlo antes de mergear.

## Preparar Supabase (una sola vez)

Crear un proyecto y correr en orden todas las migraciones de `supabase/migrations`, ya sea con
`supabase link` + `supabase db push` o pegándolas en el SQL Editor. En *Authentication → Providers →
Email* dejar activo el registro con correo.

## Conectar las redes (pestaña Cuentas)

- **YouTube:** en Google Cloud se crea un cliente OAuth de tipo **App de escritorio** con la YouTube
  Data API v3 activada. El Client ID y el secret van en *Esta PC*. Al darle Conectar se abre tu navegador.
- **TikTok:** en TikTok for Developers se crea una app con Login Kit + Content Posting API y la
  plataforma **Desktop**, con el redirect `http://127.0.0.1:47821/api/oauth/tiktok/callback`. El
  Client key y el secret van en *Esta PC*.
- **Instagram:** necesita una cuenta profesional. En la app de Meta (*Instagram API con inicio de
  sesión de Instagram*) se genera el token y se pega en la pestaña Cuentas.

## Cómo trabaja el motor

**En vivo:**
- Graba solo los últimos 6 minutos del directo en pedacitos de 4 s.
- Escucha el chat (Twitch, Kick y YouTube) y mide el audio segundo a segundo.
- Cuando el chat o el audio se disparan frente a lo normal de ese directo, corta el momento con su
  reacción y lo edita al instante.
- En Twitch también toma los clips que la gente va creando.

**Pedidos:** busca los picos sin bajar el video completo y baja en Full HD solo esos tramos. Para
encontrarlos usa la curva de "lo más visto" de YouTube, el chat, los subtítulos o, como último
recurso, solo el audio.

**Edición:**
- Transcribe palabra por palabra con Whisper.
- Con IA (si hay llave de Claude): hook verdadero, título con búsquedas, captions por red, hashtags,
  juicio de si el clip se entiende solo y corrección de nombres en los subtítulos.
- Encuadre según las caras: facecam arriba + juego abajo, seguir la cara, o fondo desenfocado.
- Zooms de golpe con sacudida y destello.
- Efectos de sonido: los propios del motor o los que suban en *Sonidos*.
- Subtítulos que cambian de letra y color en cada clip.
- Audio a -14 LUFS, video 1080×1920.

## Límites que hay que saber

- **YouTube:** lo que se sube por la API queda privado hasta que Google apruebe la app (auditoría).
- **TikTok:** sin la auditoría de TikTok llega como borrador a la bandeja de la app.
- **Supabase gratis:** tiene 1 GB de archivos. La app borra los videos ya publicados o descartados a
  los días que digan los Ajustes.
- **Derechos:** resubir clips de otros puede traer reclamos. Cada publicación lleva el crédito y el
  enlace al original; lo más seguro es trabajar con streamers que lo permitan.
