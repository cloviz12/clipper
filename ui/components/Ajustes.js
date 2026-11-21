"use client";
import { useEffect, useState } from "react";
import { sb } from "@/lib/supabase";

const CAMPOS = [
  ["duracion_clip", "Duración de los clips (seg)", "texto", "Ej: 20-45. Para Shorts funcionan mejor 15-35 s."],
  ["efectos_camara", "Efectos de cámara (zoom de golpe, sacudida, destello)", ["apagado", "bajo", "medio", "alto"]],
  ["efectos_sonido", "Efectos de sonido", ["apagado", "bajo", "medio", "alto"]],
  ["formato", "Encuadre vertical", ["auto", "split", "seguir", "blur", "crop"], "auto: si hay facecam pone cámara arriba y juego abajo; si la cámara es grande sigue la cara; si no, fondo desenfocado."],
  ["hook_en_pantalla", "Hook escrito arriba los primeros segundos", "bool"],
  ["mostrar_credito", "Crédito @canal arriba", "bool"],
  ["mayusculas", "Subtítulos en mayúsculas", "bool"],
  ["idioma", "Idioma de los subtítulos", ["es", "en", "pt", "auto"]],
  ["whisper_modelo", "Precisión de subtítulos", ["base", "small", "medium"], "small = buen balance. medium = más exacto pero más lento sin tarjeta de video."],
  ["auto_puntaje_minimo", "Puntaje mínimo para publicar solo", "numero", "Solo para canales en modo automático (0-100)."],
  ["hashtags_base", "Hashtags fijos", "lista", "Se suman a los que escribe la IA. Separados por espacio."],
  ["tiktok_modo", "TikTok", ["borrador", "directo"], "borrador: llega a la bandeja de la app de TikTok y se termina desde el celular. directo: se confirma en tanda en la pestaña TikTok y se publica solo a la hora programada."],
  ["youtube_privacidad", "Privacidad en YouTube", ["public", "unlisted", "private"]],
  ["dias_guardar_videos", "Días que se guardan los videos ya publicados", "numero"],
  ["max_clips_revisar", "Máximo de clips por revisar", "numero", "Si hay más, los más viejos se descartan solos y su video se borra de la nube (el plan gratis de Supabase tiene 1 GB). Pon 0 para no descartar nunca."],
];

export default function Ajustes() {
  const [d, setD] = useState(null);
  const [ok, setOk] = useState("");
  useEffect(() => { sb().from("ajustes").select("datos").eq("id", 1).single().then(({ data }) => setD(data?.datos || {})); }, []);
  if (!d) return null;
  async function guardar() {
    const { error } = await sb().from("ajustes").update({ datos: d, actualizado: new Date().toISOString() }).eq("id", 1);
    setOk(error ? error.message : "Guardado. El motor lo toma en menos de un minuto.");
  }
  return (
    <div className="caja" style={{ maxWidth: 720 }}>
      <h2>Ajustes del equipo</h2>
      {CAMPOS.map(([k, nom, tipo, ayuda]) => (
        <div key={k}>
          <label>{nom}</label>
          {Array.isArray(tipo) ? (
            <select value={d[k] ?? ""} onChange={(e) => setD({ ...d, [k]: e.target.value })}>
              {tipo.map((o) => <option key={o}>{o}</option>)}
            </select>
          ) : tipo === "bool" ? (
            <select value={d[k] ? "si" : "no"} onChange={(e) => setD({ ...d, [k]: e.target.value === "si" })}>
              <option>si</option><option>no</option>
            </select>
          ) : tipo === "numero" ? (
            <input type="number" value={d[k] ?? ""} onChange={(e) => setD({ ...d, [k]: Number(e.target.value) })} />
          ) : tipo === "lista" ? (
            <input value={(d[k] || []).join(" ")} onChange={(e) => setD({ ...d, [k]: e.target.value.split(/\s+/).filter(Boolean) })} />
          ) : (
            <input value={d[k] ?? ""} onChange={(e) => setD({ ...d, [k]: e.target.value })} />
          )}
          {ayuda && <div className="suave" style={{ fontSize: 12, marginTop: 3 }}>{ayuda}</div>}
        </div>
      ))}
      <div className="fila" style={{ marginTop: 16 }}>
        <button className="btn prim" onClick={guardar}>Guardar</button>
        <span className="suave">{ok}</span>
      </div>
    </div>
  );
}
