"use client";
import { useEffect, useState } from "react";
import { sb, hace, PLATAFORMAS } from "@/lib/supabase";

const MODOS = {
  en_vivo: "Tiempo real (corta los picos del directo apenas pasan)",
  destacados: "Clips más vistos del día (Twitch/Kick), cada pocas horas",
  videos: "Videos nuevos del canal (YouTube), cada pocas horas",
};

function plataformaDe(url) {
  const u = url.toLowerCase();
  if (u.includes("twitch.tv")) return "twitch";
  if (u.includes("kick.com")) return "kick";
  if (u.includes("youtu")) return "youtube";
  return "otro";
}
function nombreDe(url) {
  const m = url.match(/(?:twitch\.tv|kick\.com)\/([A-Za-z0-9_\-]+)/) || url.match(/youtube\.com\/(@[^/?]+)/);
  return m ? m[1] : url;
}

export default function EnVivo({ email }) {
  const [fuentes, setFuentes] = useState([]);
  const [nuevo, setNuevo] = useState({ url: "", modo: "en_vivo", publicacion: "revisar" });
  const cargar = () => sb().from("fuentes").select("*").order("creado").then(({ data }) => setFuentes(data || []));
  useEffect(() => {
    cargar();
    const ch = sb().channel("fuentes").on("postgres_changes", { event: "*", schema: "public", table: "fuentes" }, cargar).subscribe();
    return () => sb().removeChannel(ch);
  }, []);
  const cambiar = (id, campos) => sb().from("fuentes").update(campos).eq("id", id).then(({ error }) => error && alert(error.message));
  async function agregar(e) {
    e.preventDefault();
    const url = nuevo.url.trim();
    if (!url) return;
    const { error } = await sb().from("fuentes").insert({ ...nuevo, url, plataforma: plataformaDe(url), nombre: nombreDe(url), creado_por: email });
    if (error) alert(error.message);
    else setNuevo({ ...nuevo, url: "" });
  }
  return (
    <>
      <form className="caja" onSubmit={agregar} style={{ marginBottom: 16 }}>
        <h2>Vigilar un canal</h2>
        <div className="fila" style={{ alignItems: "flex-end" }}>
          <div style={{ flex: "2 1 300px" }}>
            <label>Canal de Twitch, Kick o YouTube</label>
            <input placeholder="https://www.twitch.tv/nombre" value={nuevo.url} onChange={(e) => setNuevo({ ...nuevo, url: e.target.value })} />
          </div>
          <div style={{ flex: "1 1 220px" }}>
            <label>Cómo</label>
            <select value={nuevo.modo} onChange={(e) => setNuevo({ ...nuevo, modo: e.target.value })}>
              {Object.entries(MODOS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </div>
          <div style={{ flex: "1 1 200px" }}>
            <label>Al tener un clip</label>
            <select value={nuevo.publicacion} onChange={(e) => setNuevo({ ...nuevo, publicacion: e.target.value })}>
              <option value="revisar">Avisarnos para aprobar (1 toque)</option>
              <option value="auto">Publicar solo si la IA lo aprueba</option>
            </select>
          </div>
          <button className="btn prim" type="submit">Agregar</button>
        </div>
      </form>

      {fuentes.length === 0 && <div className="vacio">Agrega los streamers que quieren vigilar.</div>}
      <div className="grid">
        {fuentes.map((f) => (
          <div key={f.id} className="caja">
            <div className="fila">
              <span className={`punto ${f.en_vivo ? "vivo" : ""}`} />
              <b style={{ fontSize: 16 }}>{f.nombre}</b>
              <span className="chip">{f.plataforma}</span>
              {f.en_vivo ? <span className="chip mal">EN VIVO</span> : <span className="suave" style={{ fontSize: 12 }}>{f.ultimo_chequeo ? `revisado ${hace(f.ultimo_chequeo)}` : "esperando al motor"}</span>}
              <label style={{ marginLeft: "auto", display: "flex", gap: 6, margin: 0, color: "var(--texto)" }}>
                <input type="checkbox" style={{ width: "auto" }} checked={f.activo} onChange={(e) => cambiar(f.id, { activo: e.target.checked })} /> activo
              </label>
            </div>
            {f.en_vivo && f.titulo_directo && <div className="suave" style={{ marginTop: 6 }}>{f.titulo_directo}</div>}
            <label>Modo</label>
            <select value={f.modo} onChange={(e) => cambiar(f.id, { modo: e.target.value })}>
              {Object.entries(MODOS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <label>Publicación</label>
            <select value={f.publicacion} onChange={(e) => cambiar(f.id, { publicacion: e.target.value })}>
              <option value="revisar">Avisarnos para aprobar</option>
              <option value="auto">Automática (si la IA le da el puntaje mínimo)</option>
            </select>
            {f.modo === "en_vivo" && <>
              <label>Sensibilidad: {f.sensibilidad <= 0.7 ? "muchos clips" : f.sensibilidad >= 1.5 ? "solo picos enormes" : "normal"} ({f.sensibilidad})</label>
              <input type="range" min="0.5" max="2" step="0.1" defaultValue={f.sensibilidad}
                onMouseUp={(e) => cambiar(f.id, { sensibilidad: Number(e.target.value) })}
                onTouchEnd={(e) => cambiar(f.id, { sensibilidad: Number(e.target.value) })} />
              <label>Momentos por hora que busca (se ajusta al chat de este canal)</label>
              <input type="number" min="1" max="20" step="1" defaultValue={f.opciones?.clips_por_hora || 4}
                onBlur={(e) => {
                  const n = Math.max(1, Math.min(20, Number(e.target.value) || 4));
                  if (n !== (f.opciones?.clips_por_hora || 4)) cambiar(f.id, { opciones: { ...(f.opciones || {}), clips_por_hora: n } });
                }} />
              <div className="suave" style={{ fontSize: 12, marginTop: 6 }}>
                {f.opciones?.perfil?.umbral
                  ? <>Aprendido del canal: ~{Math.round(f.opciones.perfil.gente_tipica || 0)} personas comentando cada 10 s
                    · umbral {Number(f.opciones.perfil.umbral).toFixed(1)}
                    {f.opciones.perfil.directos ? ` · ${f.opciones.perfil.directos} directo${f.opciones.perfil.directos === 1 ? "" : "s"}` : ""}</>
                  : "Todavía aprendiendo cómo reacciona este público (se calibra en los primeros 10 min del directo)."}
              </div>
            </>}
            <label>Redes</label>
            <div className="fila">
              {PLATAFORMAS.map((p) => (
                <label key={p.id} style={{ display: "flex", gap: 6, margin: 0, color: "var(--texto)" }}>
                  <input type="checkbox" style={{ width: "auto" }} checked={f.plataformas.includes(p.id)}
                    onChange={(e) => cambiar(f.id, { plataformas: e.target.checked ? [...f.plataformas, p.id] : f.plataformas.filter((x) => x !== p.id) })} />{p.nombre}
                </label>
              ))}
            </div>
            <div className="acciones">
              <a className="btn chico" href={f.url} target="_blank" rel="noreferrer">Abrir canal</a>
              <button className="btn chico peligro" onClick={() => confirm(`¿Quitar ${f.nombre}?`) && sb().from("fuentes").delete().eq("id", f.id).then(cargar)}>Quitar</button>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
