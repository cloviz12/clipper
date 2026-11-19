"use client";
import { useEffect, useState } from "react";
import { sb } from "@/lib/supabase";

const CATS = {
  whoosh: "Transición al empezar", impacto: "Golpe con cada zoom", pop: "Cuando aparece el hook",
  riser: "Sube antes del momento", glitch: "Golpe alterno", ding: "Cierre", risa: "Risas", meme: "Memes / remates",
};

export default function Sonidos() {
  const [archivos, setArchivos] = useState({});
  const [cat, setCat] = useState("impacto");
  const [subiendo, setSubiendo] = useState(false);
  async function cargar() {
    const out = {};
    for (const c of Object.keys(CATS)) {
      const { data } = await sb().storage.from("sfx").list(c, { limit: 200 });
      out[c] = (data || []).filter((f) => f.name && !f.name.startsWith("."));
    }
    setArchivos(out);
  }
  useEffect(() => { cargar(); }, []);
  async function subir(e) {
    setSubiendo(true);
    for (const f of e.target.files) {
      const nombre = f.name.replace(/[^\w.\-]+/g, "_");
      const { error } = await sb().storage.from("sfx").upload(`${cat}/${nombre}`, f, { upsert: true });
      if (error) alert(`${f.name}: ${error.message}`);
    }
    e.target.value = "";
    setSubiendo(false);
    cargar();
  }
  async function oir(path) {
    const { data } = await sb().storage.from("sfx").createSignedUrl(path, 600);
    if (data) new Audio(data.signedUrl).play();
  }
  return (
    <>
      <div className="caja" style={{ marginBottom: 16 }}>
        <h2>Librería de efectos de sonido</h2>
        <p className="suave" style={{ marginTop: 0 }}>
          El motor ya trae sonidos propios (fabricados por él, sin problemas de derechos). Si suben los suyos aquí, los usa primero
          y los va rotando para que ningún clip suene igual. Usen solo sonidos con licencia para uso comercial (por ejemplo los
          generados en ElevenLabs SFX o packs comprados).
        </p>
        <div className="fila">
          <select value={cat} onChange={(e) => setCat(e.target.value)} style={{ width: 280 }}>
            {Object.entries(CATS).map(([k, v]) => <option key={k} value={k}>{k} — {v}</option>)}
          </select>
          <label className="btn prim" style={{ margin: 0 }}>
            {subiendo ? "Subiendo..." : "Subir audios (mp3, wav)"}
            <input type="file" accept="audio/*" multiple hidden onChange={subir} disabled={subiendo} />
          </label>
        </div>
      </div>
      <div className="grid">
        {Object.entries(CATS).map(([c, desc]) => (
          <div key={c} className="caja">
            <h3>{c} <span className="suave" style={{ fontWeight: 400, fontSize: 12 }}>{desc}</span></h3>
            {(archivos[c] || []).length === 0 && <div className="suave" style={{ fontSize: 12 }}>Usando los sonidos del motor.</div>}
            <div className="lista">
              {(archivos[c] || []).map((f) => (
                <div key={f.name} className="fila">
                  <span style={{ flex: 1, wordBreak: "break-all" }}>{f.name}</span>
                  <button className="btn chico" onClick={() => oir(`${c}/${f.name}`)}>▶</button>
                  <button className="btn chico peligro" onClick={() => sb().storage.from("sfx").remove([`${c}/${f.name}`]).then(cargar)}>✕</button>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
