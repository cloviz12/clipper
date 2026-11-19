# CLIPPER

App de escritorio (Windows) para sacar clips de streamers en tiempo real. Detecta el momento, lo
edita como Short y lo publica en YouTube Shorts, TikTok e Instagram Reels. La edición incluye
subtítulos animados, hook, encuadre por caras, zooms, sacudidas, destellos y efectos de sonido.

Cada persona del equipo instala la app en su PC. Las dos apps comparten los mismos clips, canales y
ajustes a través de Supabase, así que cualquiera puede aprobar o publicar desde su computadora.

```
app/        App de escritorio: ventana + bandeja + servidor local + instalador
ui/         Pantallas de la app (Next.js exportado como archivos estáticos)
worker/     Motor: vigila directos, edita y publica (va dentro de la app y en el servidor)
servidor/   Instalación del motor en un servidor 24/7 (Docker + actualización sola)
supabase/   Base de datos compartida (migraciones)
.github/    GitHub construye el instalador solo y lo publica en Releases
```

## Instalar

1. En GitHub ve a **Releases** y descarga `CLIPPER-Setup-x.y.z.exe`. El compañero tiene que estar
   agregado como colaborador del repo para poder verlo.
2. Instálalo. No pide administrador y trae ffmpeg, el descargador y todo lo demás adentro.

**El dueño (el que tiene Supabase y las cuentas de los canales) entra primero:**

3. Elige **Soy el dueño: configurar desde cero** y llena la URL y las llaves de Supabase y, si quiere,
   las de Claude, Google y TikTok.
4. Crea su cuenta (la primera cuenta queda como dueña).
5. En **Equipo** agrega el correo del compañero y le manda el **código de invitación** (botón *Copiar código*).

**El compañero, después:**

6. Elige **Me invitaron: tengo un código**, pega el código y crea su cuenta con el correo que el dueño agregó.
7. CLIPPER recibe solo las llaves del dueño y se reinicia listo. No tiene que llenar nada más.

El código solo lleva la dirección del proyecto y la llave pública; las llaves secretas se entregan
únicamente a quien inicia sesión con un correo de la lista de Equipo. Si el dueño cambia una llave en
*Esta PC*, a los demás les llega sola la próxima vez que abran CLIPPER.

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

Cada PR también construye el instalador y lo publica en Releases como *pre-release* de prueba, para probarlo antes de mergear. Las apps instaladas no se actualizan a esas versiones de prueba.

## Motor en la nube (sin depender de ningún PC)

Con la app basta **un** PC prendido; el otro puede estar apagado. Para no depender de ninguno, el motor
se puede dejar en un servidor 24/7. Cuando el servidor está encendido, él vigila los directos y hace
los pedidos; los PCs se quedan solo para manejar y aprobar (y retoman el trabajo si el servidor se cae).

1. Conseguir un servidor Linux (Ubuntu). Opción gratis: Oracle Cloud *Always Free* con una instancia
   **Ampere A1 de 2 OCPU y 12 GB**. Con 2 núcleos conviene poner *Precisión de subtítulos = base* en
   Ajustes para que edite más rápido.
2. Entrar por SSH y correr (con el token de GitHub de solo lectura):
   ```
   curl -fsSL -H "Authorization: Bearer TU_TOKEN" https://raw.githubusercontent.com/cloviz12/clipper/main/servidor/instalar.sh | sudo GITHUB_TOKEN=TU_TOKEN bash
   ```
   Pide las llaves una vez y deja el motor corriendo siempre.
3. Se actualiza solo: cada 10 minutos revisa `main` y, si cambió, se reconstruye.

YouTube a veces bloquea las descargas desde servidores. Si pasa, se exportan las cookies de una sesión
de YouTube (formato *cookies.txt*) y se copian al servidor en
`/var/lib/docker/volumes/servidor_datos/_data/cookies_youtube.txt`. Twitch y Kick no tienen ese problema.

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
- Lee el chat como una persona: no cuenta mensajes, cuenta **gente distinta reaccionando a lo mismo**.
  Corta cuando buena parte del chat se ríe a la vez (KEKW, jajaja, xd, ICANT...), se sorprende
  (WTF, QUEEE, ???, NOOO), explota de hype (GOOOL, VAMOS) o se pone a hablar de una misma cosa
  ("el gato", "penal"...). Un raid saludando, el spam de una sola persona, los bots y los comandos no
  cuentan. El audio suma cuando hay gritos o risas.
- Cada clip lleva en el panel qué hizo el chat (por ejemplo `chat: risa (62%)` o
  `chat habla de «gato»`) y la IA usa eso para escribir el hook y el título.
- En Twitch y Kick vigila cada 20 s los clips que crea la gente. Si **varias personas distintas
  sacan clip al mismo tiempo** (menos de 45 s entre uno y otro), es un momento seguro: lo corta de la
  grabación propia, en mejor calidad y con la reacción completa, y en el panel sale
  `3 clips de la comunidad a la vez`. Un clip suelto se usa tal cual si nadie más clipea lo mismo.

**Pedidos:** busca los picos sin bajar el video completo (en VODs con chat usa la misma lectura de
risas y temas; en VODs de Twitch también busca dónde sacó clip la gente, y los tramos que clipearon
varias personas pesan más que cualquier otra señal) y baja en Full HD solo esos tramos. Para
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
