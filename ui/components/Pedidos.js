"use client";
import { useEffect, useState } from "react";
import { sb, hace, PLATAFORMAS } from "@/lib/supabase";

export default function Pedidos({ email }) {
  const [lista, setLista] = useState([]);
  const [p, setP] = useState({ url: "", clips: 3, duracion: "20-45", publicar: "revisar", plataformas: PLATAFORMAS.map((x) => x.id) });
  const cargar = () => sb().from("trabajos").select("*").order("creado", { ascending: false }).limit(40).then(({ data }) => setLista(data || []));
  useEffect(() => {
    cargar();
    const ch = sb().channel("trabajos").on("postgres_changes", { event: "*", schema: "public", table: "trabajos" }, cargar).subscribe();
    return () => sb().removeChannel(ch);
  }, []);
  async function pedir(e) {
    e.preventDefault();
    const urls = p.url.split(/\s+/).map((u) => u.trim()).filter((u) => u.startsWith("http"));
    if (!urls.length) return;
    const filas = urls.map((url) => ({
      url, clips: Number(p.clips) || 3, duracion: p.duracion, creado_por: email,
      opciones: { publicar: p.publicar, plataformas: p.plataformas },
    }));
    const { error } = await sb().from("trabajos").insert(filas);
    if (error) alert(error.message);
    else setP({ ...p, url: "" });
  }
  return (
    <>
      <form className="caja" onSubmit={pedir} style={{ marginBottom: 16 }}>
        <h2>Sacar clips de un link</h2>
        <p className="suave" style={{ marginTop: 0 }}>
          Video o directo ya terminado de YouTube, VOD de Twitch/Kick, o un canal (saca sus clips más vistos o sus últimos videos).
          Nunca baja el video completo: busca los picos y baja solo esos tramos.
        </p>
        <label>Links (uno por línea)</label>
        <textarea value={p.url} onChange={(e) => setP({ ...p, url: e.target.value })} placeholder="https://www.youtube.com/watch?v=..." />
        <div className="fila" style={{ alignItems: "flex-end" }}>
          <div style={{ width: 110 }}><label>Clips por link</label>
            <input type="number" min="1" max="10" value={p.clips} onChange={(e) => setP({ ...p, clips: e.target.value })} /></div>
          <div style={{ width: 140 }}><label>Duración (seg)</label>
            <input value={p.duracion} onChange={(e) => setP({ ...p, duracion: e.target.value })} /></div>
          <div style={{ width: 240 }}><label>Al terminar</label>
            <select value={p.publicar} onChange={(e) => setP({ ...p, publicar: e.target.value })}>
              <option value="revisar">Dejar para revisar</option>
              <option value="auto">Publicar si la IA lo aprueba</option>
            </select></div>
          <button className="btn prim" type="submit">Pedir clips</button>
        </div>
      </form>
      <div className="caja lista">
        {lista.length === 0 && <div className="suave">Sin pedidos todavía.</div>}
        {lista.map((t) => (
          <div key={t.id}>
            <div className="fila">
              <span className={`chip ${t.estado === "terminado" ? "ok" : t.estado === "error" ? "mal" : "ambar"}`}>{t.estado}</span>
              <a href={t.url} target="_blank" rel="noreferrer" style={{ wordBreak: "break-all" }}>{t.url}</a>
              <span className="suave" style={{ marginLeft: "auto", fontSize: 12 }}>{t.creado_por} · {hace(t.creado)}</span>
            </div>
            {(t.progreso || t.error) && <div className="suave" style={{ fontSize: 12, marginTop: 4 }}>{t.error || t.progreso}</div>}
          </div>
        ))}
      </div>
    </>
  );
}
