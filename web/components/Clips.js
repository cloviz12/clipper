"use client";
import { useEffect, useState } from "react";
import { sb, hace, PLATAFORMAS } from "@/lib/supabase";

const FILTROS = [
  ["revisar", "Para revisar", ["revisar"]],
  ["salida", "Publicando", ["aprobado", "programado", "publicando", "procesando"]],
  ["publicado", "Publicados", ["publicado"]],
  ["error", "Con error", ["error"]],
  ["descartado", "Descartados", ["descartado"]],
];
const urls = {};

async function firmada(path) {
  if (!path) return null;
  if (urls[path] && urls[path].vence > Date.now()) return urls[path].url;
  const { data } = await sb().storage.from("clips").createSignedUrl(path, 3600);
  if (data?.signedUrl) urls[path] = { url: data.signedUrl, vence: Date.now() + 3500 * 1000 };
  return data?.signedUrl;
}

function Puntaje({ v }) {
  if (v == null) return null;
  const c = v >= 70 ? "alto" : v >= 45 ? "medio" : "bajo";
  return <span className={`puntaje ${c}`} title="Probabilidad de funcionar como Short (IA)">{Math.round(v)}</span>;
}

function Tarjeta({ c, email }) {
  const [mini, setMini] = useState(null);
  const [video, setVideo] = useState(null);
  const [editar, setEditar] = useState(false);
  const [t, setT] = useState(c.textos || {});
  const [cuando, setCuando] = useState("");
  const [plats, setPlats] = useState(c.plataformas || []);

  useEffect(() => { firmada(c.miniatura_path).then(setMini); }, [c.miniatura_path]);

  const cambiar = (campos) => sb().from("clips").update(campos).eq("id", c.id).then(({ error }) => error && alert(error.message));
  const guardar = () => { cambiar({ textos: t, titulo: t.youtube?.titulo, plataformas: plats }); setEditar(false); };
  const ver = async () => setVideo(await firmada(c.video_path));
  const bajar = async () => window.open(await firmada(c.video_path), "_blank");

  return (
    <div className="caja clip">
      <div className="vid" onClick={video ? undefined : ver}>
        {video ? <video src={video} controls autoPlay playsInline /> : <>
          {mini && <img src={mini} alt="" />}
          {c.video_path && <div className="play">▶</div>}
        </>}
      </div>
      <div style={{ minWidth: 0 }}>
        <div className="fila" style={{ gap: 6 }}>
          <Puntaje v={c.puntaje} />
          <b>{c.canal}</b>
          <span className="chip">{c.origen?.replace("_", " ")}</span>
          <span className="suave" style={{ fontSize: 12 }}>{hace(c.detectado_en || c.creado)}</span>
        </div>
        <div className="hook">{c.hook || c.titulo}</div>
        {c.ia?.razon && <div className="suave" style={{ fontSize: 12 }}>IA: {c.ia.razon}</div>}
        <div className="fila" style={{ gap: 4, marginTop: 6 }}>
          {(c.senales || []).map((s) => <span key={s} className="chip">{s}</span>)}
          {c.ia?.encuadre && <span className="chip">{c.ia.encuadre}</span>}
          {c.duracion && <span className="chip">{Math.round(c.duracion)} s</span>}
        </div>
        <div className="fila" style={{ gap: 4, marginTop: 6 }}>
          {PLATAFORMAS.filter((p) => (c.plataformas || []).includes(p.id)).map((p) => {
            const pub = c.publicaciones?.[p.id], err = c.errores?.[p.id];
            return (
              <span key={p.id} className={`chip ${pub ? "ok" : err ? "mal" : ""}`} title={err || pub?.estado || ""}>
                {pub?.url ? <a href={pub.url} target="_blank" rel="noreferrer">{p.nombre} ✓</a> : `${p.nombre}${pub ? " ✓" : err ? " ✗" : ""}`}
              </span>
            );
          })}
          {c.estado === "programado" && <span className="chip ambar">programado {new Date(c.publicar_en).toLocaleString("es-CO")}</span>}
        </div>

        {editar && (
          <div>
            <label>Título YouTube</label>
            <input value={t.youtube?.titulo || ""} onChange={(e) => setT({ ...t, youtube: { ...t.youtube, titulo: e.target.value } })} />
            <label>Descripción YouTube</label>
            <textarea value={t.youtube?.descripcion || ""} onChange={(e) => setT({ ...t, youtube: { ...t.youtube, descripcion: e.target.value } })} />
            <label>Caption TikTok</label>
            <textarea value={t.tiktok?.caption || ""} onChange={(e) => setT({ ...t, tiktok: { caption: e.target.value } })} />
            <label>Caption Instagram</label>
            <textarea value={t.instagram?.caption || ""} onChange={(e) => setT({ ...t, instagram: { caption: e.target.value } })} />
            <label>Redes</label>
            <div className="fila">
              {PLATAFORMAS.map((p) => (
                <label key={p.id} style={{ display: "flex", gap: 6, margin: 0, color: "var(--texto)" }}>
                  <input type="checkbox" style={{ width: "auto" }} checked={plats.includes(p.id)}
                    onChange={(e) => setPlats(e.target.checked ? [...plats, p.id] : plats.filter((x) => x !== p.id))} />{p.nombre}
                </label>
              ))}
            </div>
            {c.transcripcion && <><label>Transcripción</label><div className="suave" style={{ fontSize: 12 }}>{c.transcripcion}</div></>}
          </div>
        )}

        <div className="acciones">
          {["revisar", "error", "descartado"].includes(c.estado) && (
            <button className="btn prim" onClick={() => cambiar({ estado: "aprobado", aprobado_por: email, publicar_en: null })}>
              {c.estado === "error" ? "Reintentar" : "Publicar ya"}
            </button>
          )}
          {c.estado === "revisar" && (
            <>
              <input type="datetime-local" value={cuando} onChange={(e) => setCuando(e.target.value)} style={{ width: 190 }} />
              <button className="btn" disabled={!cuando}
                onClick={() => cambiar({ estado: "programado", publicar_en: new Date(cuando).toISOString(), aprobado_por: email })}>Programar</button>
            </>
          )}
          {editar ? <button className="btn" onClick={guardar}>Guardar textos</button>
            : <button className="btn" onClick={() => setEditar(true)}>Editar textos</button>}
          {c.video_path && <button className="btn" onClick={bajar}>Descargar</button>}
          {["revisar", "programado", "error"].includes(c.estado) && (
            <button className="btn peligro" onClick={() => cambiar({ estado: "descartado" })}>Descartar</button>
          )}
        </div>
      </div>
    </div>
  );
}

export default function Clips({ email }) {
  const [filtro, setFiltro] = useState("revisar");
  const [clips, setClips] = useState([]);
  useEffect(() => {
    const estados = FILTROS.find((f) => f[0] === filtro)[2];
    const cargar = () => sb().from("clips").select("*").in("estado", estados).order("creado", { ascending: false }).limit(60)
      .then(({ data }) => setClips(data || []));
    cargar();
    const ch = sb().channel("clips-" + filtro).on("postgres_changes", { event: "*", schema: "public", table: "clips" }, cargar).subscribe();
    return () => sb().removeChannel(ch);
  }, [filtro]);
  return (
    <>
      <div className="fila" style={{ marginBottom: 16 }}>
        {FILTROS.map(([id, nom]) => (
          <button key={id} className={`btn chico ${filtro === id ? "prim" : ""}`} onClick={() => setFiltro(id)}>{nom}</button>
        ))}
      </div>
      {clips.length === 0 ? (
        <div className="vacio">
          {filtro === "revisar" ? "Nada por revisar. Cuando un canal en vivo tenga un pico, el clip aparece aquí con un sonido." : "No hay clips aquí."}
        </div>
      ) : (
        <div className="grid">{clips.map((c) => <Tarjeta key={c.id + c.estado} c={c} email={email} />)}</div>
      )}
    </>
  );
}
