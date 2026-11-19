"use client";
import { useEffect, useMemo, useState } from "react";
import { sb, hace } from "@/lib/supabase";
import { local } from "@/lib/local";
import { firmada } from "./Clips";

// Publicacion directa en TikTok: TikTok exige que una persona confirme cada video (privacidad elegida a mano,
// interacciones apagadas de entrada, divulgacion comercial y consentimiento). Aqui se confirma en tanda y el
// motor los publica solos, espaciados, a la hora programada.
const PRIVACIDAD = {
  PUBLIC_TO_EVERYONE: "Todos",
  MUTUAL_FOLLOW_FRIENDS: "Amigos (se siguen mutuamente)",
  FOLLOWER_OF_CREATOR: "Seguidores",
  SELF_ONLY: "Solo yo",
};
const CADA = [[30, "cada 30 min"], [60, "cada 1 hora"], [90, "cada 1 h 30 min"], [120, "cada 2 horas"], [180, "cada 3 horas"]];
const MUSICA = "https://www.tiktok.com/legal/page/global/music-usage-confirmation/en";
const MARCA = "https://www.tiktok.com/legal/page/global/bc-policy/en";

function tituloDe(c) {
  const cap = c.textos?.tiktok?.caption || c.titulo || c.hook || "";
  const tags = (c.hashtags || []).join(" ");
  return `${cap}${tags ? `\n${tags}` : ""}`.slice(0, 2200);
}

function Fila({ c, max, sel, titulo, onSel, onTitulo }) {
  const [video, setVideo] = useState(null);
  const largo = max && c.duracion && c.duracion > max;
  return (
    <div className="caja clip" style={{ opacity: largo ? 0.6 : 1 }}>
      <div className="vid" onClick={video ? undefined : async () => setVideo(await firmada(c.video_path))}>
        {video ? <video src={video} controls autoPlay playsInline /> : <div className="play">▶</div>}
      </div>
      <div style={{ minWidth: 0 }}>
        <label style={{ display: "flex", gap: 8, margin: 0, color: "var(--texto)" }}>
          <input type="checkbox" style={{ width: "auto" }} checked={sel && !largo} disabled={largo}
            onChange={(e) => onSel(e.target.checked)} />
          <b>{c.canal}</b>
          <span className="suave" style={{ fontSize: 12 }}>{hace(c.detectado_en || c.creado)}{c.duracion ? ` · ${Math.round(c.duracion)} s` : ""}</span>
        </label>
        <div className="hook">{c.hook || c.titulo}</div>
        {largo && <div className="suave" style={{ fontSize: 12 }}>Dura más de lo que TikTok permite en esta cuenta ({max} s).</div>}
        <label>Texto del video</label>
        <textarea rows={3} maxLength={2200} value={titulo} onChange={(e) => onTitulo(e.target.value)} />
      </div>
    </div>
  );
}

export default function TikTok({ sesion }) {
  const [clips, setClips] = useState([]);
  const [creador, setCreador] = useState(null);
  const [errorCreador, setErrorCreador] = useState("");
  const [sel, setSel] = useState({});
  const [titulos, setTitulos] = useState({});
  const [priv, setPriv] = useState("");                 // sin valor por defecto: TikTok lo exige
  const [com, setCom] = useState(false);
  const [duo, setDuo] = useState(false);
  const [stitch, setStitch] = useState(false);
  const [comercial, setComercial] = useState(false);
  const [miMarca, setMiMarca] = useState(false);
  const [deMarca, setDeMarca] = useState(false);
  const [cada, setCada] = useState(90);
  const [msg, setMsg] = useState("");

  const cargar = () => sb().from("clips").select("*").not("tiktok", "is", null).order("creado")
    .then(({ data }) => setClips(data || []));
  const pedirCreador = () => {
    setErrorCreador("");
    local("/api/tiktok/creador", { token: sesion.access_token }).then(setCreador)
      .catch((e) => { setCreador(null); setErrorCreador(String(e.message || e)); });
  };
  useEffect(() => {
    cargar();
    pedirCreador();
    const ch = sb().channel("tiktok").on("postgres_changes", { event: "*", schema: "public", table: "clips" }, cargar).subscribe();
    return () => { sb().removeChannel(ch); };
  }, []);

  const esperando = clips.filter((c) => c.tiktok?.estado === "esperando" && c.estado !== "descartado" && c.video_path);
  const programados = clips.filter((c) => ["programado", "publicando"].includes(c.tiktok?.estado))
    .sort((a, b) => new Date(a.tiktok.en) - new Date(b.tiktok.en));
  const recientes = clips.filter((c) => ["publicado", "error"].includes(c.tiktok?.estado)).slice(-10).reverse();
  const max = creador?.max_video_post_duration_sec;
  const elegidos = esperando.filter((c) => sel[c.id] !== false && !(max && c.duracion > max));
  const opciones = creador?.privacy_level_options || [];

  // el contenido de marca no puede ser privado
  useEffect(() => { if (comercial && deMarca && priv === "SELF_ONLY") setPriv(""); }, [comercial, deMarca, priv]);

  const falta = !creador ? "Conecta TikTok para continuar"
    : !elegidos.length ? "Elige al menos un video"
      : !priv ? "Elige quién puede ver los videos"
        : comercial && !miMarca && !deMarca ? "Indica si promocionas tu marca, contenido de marca o ambos"
          : "";

  async function programar() {
    setMsg("");
    const ultima = programados.length ? new Date(programados[programados.length - 1].tiktok.en).getTime() : 0;
    let t = Math.max(Date.now() + 60 * 1000, ultima + cada * 60 * 1000);
    const ahora = new Date().toISOString();
    for (const c of elegidos) {
      const tiktok = {
        estado: "programado", en: new Date(t).toISOString(), confirmado_por: sesion.user.email, confirmado_en: ahora,
        post: {
          title: titulos[c.id] ?? tituloDe(c), privacy_level: priv,
          disable_comment: !com || !!creador.comment_disabled, disable_duet: !duo || !!creador.duet_disabled,
          disable_stitch: !stitch || !!creador.stitch_disabled,
          brand_organic_toggle: comercial && miMarca, brand_content_toggle: comercial && deMarca,
        },
      };
      const { error } = await sb().from("clips").update({ tiktok }).eq("id", c.id);
      if (error) { setMsg(error.message); return; }
      t += cada * 60 * 1000;
    }
    setMsg(`Listo: ${elegidos.length} videos programados. Se publican solos; cada uno puede tardar unos minutos en aparecer en tu perfil de TikTok.`);
    setPriv("");
    cargar();
  }

  const volver = (c) => sb().from("clips").update({ tiktok: { estado: "esperando" } }).eq("id", c.id).then(cargar);
  const quitar = (c) => sb().from("clips").update({ tiktok: { estado: "descartado" } }).eq("id", c.id).then(cargar);

  const etiqueta = useMemo(() => (!comercial ? "" : deMarca ? "Tus videos se marcarán como «Colaboración pagada»."
    : miMarca ? "Tus videos se marcarán como «Contenido promocional»." : ""), [comercial, miMarca, deMarca]);

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div className="caja" style={{ maxWidth: 760 }}>
        <h2>Publicar en TikTok</h2>
        {creador ? (
          <div className="fila" style={{ gap: 10 }}>
            {creador.creator_avatar_url && <img src={creador.creator_avatar_url} alt="" width={40} height={40} style={{ borderRadius: "50%" }} />}
            <div>Se publicará en <b>{creador.creator_nickname}</b>{creador.creator_username ? <span className="suave"> @{creador.creator_username}</span> : null}</div>
          </div>
        ) : (
          <p className="suave">{errorCreador || "Consultando la cuenta de TikTok..."}{" "}
            {errorCreador && <button className="btn chico" onClick={pedirCreador}>Reintentar</button>}</p>
        )}

        <label>Quién puede ver estos videos *</label>
        <select value={priv} onChange={(e) => setPriv(e.target.value)} disabled={!creador}>
          <option value="" disabled>Elige una opción</option>
          {opciones.map((o) => (
            <option key={o} value={o} disabled={o === "SELF_ONLY" && comercial && deMarca}>
              {PRIVACIDAD[o] || o}{o === "SELF_ONLY" && comercial && deMarca ? " (no disponible para contenido de marca)" : ""}
            </option>
          ))}
        </select>

        <label>Permitir a los usuarios</label>
        <div className="fila">
          {[["Comentar", com, setCom, creador?.comment_disabled], ["Dúo", duo, setDuo, creador?.duet_disabled],
            ["Stitch", stitch, setStitch, creador?.stitch_disabled]].map(([n, v, set, off]) => (
            <label key={n} style={{ display: "flex", gap: 6, margin: 0, color: off ? "var(--suave)" : "var(--texto)" }}
              title={off ? "Desactivado en la configuración de tu cuenta de TikTok" : ""}>
              <input type="checkbox" style={{ width: "auto" }} checked={v && !off} disabled={!creador || off}
                onChange={(e) => set(e.target.checked)} />{n}
            </label>
          ))}
        </div>

        <label style={{ display: "flex", gap: 8, color: "var(--texto)", marginTop: 14 }}>
          <input type="checkbox" style={{ width: "auto" }} checked={comercial} onChange={(e) => setComercial(e.target.checked)} />
          Divulgar contenido comercial (los videos promocionan una marca, producto o servicio)
        </label>
        {comercial && (
          <div style={{ paddingLeft: 24 }}>
            <label style={{ display: "flex", gap: 8, color: "var(--texto)", margin: "4px 0" }}>
              <input type="checkbox" style={{ width: "auto" }} checked={miMarca} onChange={(e) => setMiMarca(e.target.checked)} />
              Tu marca: promocionas tu propio negocio
            </label>
            <label style={{ display: "flex", gap: 8, color: "var(--texto)", margin: "4px 0" }}>
              <input type="checkbox" style={{ width: "auto" }} checked={deMarca} onChange={(e) => setDeMarca(e.target.checked)} />
              Contenido de marca: promocionas a otra marca o a un tercero
            </label>
            {etiqueta && <div className="suave" style={{ fontSize: 13 }}>{etiqueta}</div>}
          </div>
        )}

        <label>Ritmo de publicación</label>
        <select value={cada} onChange={(e) => setCada(Number(e.target.value))}>
          {CADA.map(([v, n]) => <option key={v} value={v}>Uno {n}</option>)}
        </select>

        <p className="suave" style={{ fontSize: 13 }}>
          Al publicar, aceptas la <a href={MUSICA} target="_blank" rel="noreferrer">Confirmación de uso de música</a> de TikTok
          {comercial && deMarca ? <> y su <a href={MARCA} target="_blank" rel="noreferrer">Política de contenido de marca</a></> : null}.
        </p>
        <div className="fila">
          <button className="btn prim" disabled={!!falta} onClick={programar}>
            Programar {elegidos.length} video{elegidos.length === 1 ? "" : "s"} en TikTok
          </button>
          <span className="suave">{falta || msg}</span>
        </div>
      </div>

      {esperando.length === 0
        ? <p className="suave">No hay videos esperando. Cuando un clip se apruebe, aparece aquí para confirmarlo.</p>
        : esperando.map((c) => (
          <Fila key={c.id} c={c} max={max} sel={sel[c.id] !== false} titulo={titulos[c.id] ?? tituloDe(c)}
            onSel={(v) => setSel({ ...sel, [c.id]: v })} onTitulo={(v) => setTitulos({ ...titulos, [c.id]: v })} />
        ))}

      {programados.length > 0 && (
        <div className="caja" style={{ maxWidth: 760 }}>
          <h2>Programados</h2>
          {programados.map((c) => (
            <div key={c.id} className="fila" style={{ justifyContent: "space-between" }}>
              <span>{c.tiktok.estado === "publicando" ? "Publicando ahora" : new Date(c.tiktok.en).toLocaleString("es-CO", { dateStyle: "short", timeStyle: "short" })}
                {" · "}<b>{c.canal}</b> · {c.hook || c.titulo}</span>
              {c.tiktok.estado === "programado" && <button className="btn chico" onClick={() => volver(c)}>Cancelar</button>}
            </div>
          ))}
        </div>
      )}

      {recientes.length > 0 && (
        <div className="caja" style={{ maxWidth: 760 }}>
          <h2>Últimos</h2>
          {recientes.map((c) => (
            <div key={c.id} className="fila" style={{ justifyContent: "space-between" }}>
              <span>{c.tiktok.estado === "publicado" ? "✓" : "✗"} <b>{c.canal}</b> · {c.hook || c.titulo}
                {c.tiktok.estado === "error" && <span className="suave"> — {c.tiktok.error}</span>}</span>
              {c.tiktok.estado === "error" && (
                <span className="fila" style={{ gap: 6 }}>
                  <button className="btn chico" onClick={() => volver(c)}>Volver a confirmar</button>
                  <button className="btn chico peligro" onClick={() => quitar(c)}>Quitar</button>
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
