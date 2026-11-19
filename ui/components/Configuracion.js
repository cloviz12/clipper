"use client";
import { useEffect, useState } from "react";
import { local } from "@/lib/local";
import { leerCodigo } from "@/lib/invitacion";

const CAMPOS = [
  ["supabase_url", "URL del proyecto de Supabase", "https://xxxx.supabase.co", true],
  ["supabase_anon", "Llave pública (anon / publishable) de Supabase", "", true],
  ["supabase_service", "Llave secreta (service_role) de Supabase", "Solo se guarda en esta PC", true, true],
  ["anthropic_key", "Llave de Claude (Anthropic) para hooks, títulos y juicio de calidad", "Opcional pero recomendada", false, true],
  ["google_client_id", "YouTube: Client ID (app de escritorio en Google Cloud)", "", false],
  ["google_client_secret", "YouTube: Client secret", "", false, true],
  ["tiktok_client_key", "TikTok: Client key", "", false],
  ["tiktok_client_secret", "TikTok: Client secret", "", false, true],
  ["nombre_motor", "Nombre de esta PC en el panel", "Ej: pc-juan", false],
];

export default function Configuracion({ inicial, onListo }) {
  const [d, setD] = useState({});
  const [msg, setMsg] = useState("");
  const [motor, setMotor] = useState(null);
  const [modo, setModo] = useState(inicial ? null : "dueno");
  const [codigo, setCodigo] = useState("");
  useEffect(() => {
    local("/api/configuracion").then(setD).catch(() => {});
    if (!inicial) local("/api/motor").then(setMotor).catch(() => {});
  }, [inicial]);
  async function guardar(e) {
    e.preventDefault();
    try {
      await local("/api/configuracion", d);
      setMsg("Guardado. El motor se reinicia con estos datos.");
      onListo?.();
    } catch (err) {
      setMsg(String(err.message || err));
    }
  }
  async function unirme(e) {
    e.preventDefault();
    try {
      await local("/api/configuracion", { ...leerCodigo(codigo), nombre_motor: d.nombre_motor || "" });
      onListo?.();
    } catch (err) {
      setMsg(String(err.message || err));
    }
  }
  if (modo === null) {
    return (
      <div className="login caja" style={{ maxWidth: 520 }}>
        <div className="logo" style={{ marginBottom: 6 }}>CLIP<span>PER</span></div>
        <h2>¿Cómo vas a usar CLIPPER?</h2>
        <button className="btn prim" style={{ width: "100%", marginTop: 8 }} onClick={() => setModo("invitado")}>
          Me invitaron: tengo un código
        </button>
        <p className="suave" style={{ fontSize: 13 }}>Tu compañero ya configuró todo. Solo pegas el código y entras con tu correo.</p>
        <button className="btn" style={{ width: "100%", marginTop: 8 }} onClick={() => setModo("dueno")}>
          Soy el dueño: configurar desde cero
        </button>
        <p className="suave" style={{ fontSize: 13 }}>Tienes el proyecto de Supabase y las llaves de las redes.</p>
      </div>
    );
  }
  if (modo === "invitado") {
    return (
      <form className="login caja" style={{ maxWidth: 520 }} onSubmit={unirme}>
        <div className="logo" style={{ marginBottom: 6 }}>CLIP<span>PER</span></div>
        <h2>Unirme a mi equipo</h2>
        <p className="suave" style={{ marginTop: 0 }}>
          Pídele a tu compañero el código: está en su CLIPPER, pestaña <b>Equipo</b>. Y que agregue ahí tu correo.
        </p>
        <label>Código de invitación *</label>
        <textarea rows={4} required value={codigo} placeholder="CLIPPER-..." style={{ width: "100%", fontFamily: "monospace", fontSize: 12 }}
          onChange={(e) => setCodigo(e.target.value)} />
        <label>Nombre de esta PC en el panel</label>
        <input placeholder="Ej: pc-juan" value={d.nombre_motor ?? ""} onChange={(e) => setD({ ...d, nombre_motor: e.target.value })} />
        <div className="fila" style={{ marginTop: 16 }}>
          <button className="btn prim" type="submit">Continuar</button>
          <button className="btn" type="button" onClick={() => { setModo(null); setMsg(""); }}>Volver</button>
        </div>
        {msg && <p className="suave">{msg}</p>}
      </form>
    );
  }
  return (
    <form className={inicial ? "login caja" : "caja"} style={{ maxWidth: 640 }} onSubmit={guardar}>
      {inicial && <div className="logo" style={{ marginBottom: 6 }}>CLIP<span>PER</span></div>}
      <h2>{inicial ? "Configurar esta PC" : "Esta PC"}</h2>
      <p className="suave" style={{ marginTop: 0 }}>
        Los dos usan el mismo proyecto de Supabase para ver los mismos clips. Las llaves se comparten solas con tu equipo
        (solo con los correos de la pestaña Equipo), así tus compañeros no tienen que llenarlas.
        Las llaves secretas quedan ocultas; déjalas vacías para no cambiarlas.
      </p>
      {CAMPOS.map(([k, nom, ph, req, secreto]) => (
        <div key={k}>
          <label>{nom}{req ? " *" : ""}</label>
          <input type={secreto ? "password" : "text"} placeholder={secreto && d[`${k}_guardada`] ? "•••••• (guardada)" : ph}
            value={d[k] ?? ""} required={req && !(secreto && d[`${k}_guardada`])}
            onChange={(e) => setD({ ...d, [k]: e.target.value })} />
        </div>
      ))}
      <label style={{ display: "flex", gap: 8, color: "var(--texto)", marginTop: 14 }}>
        <input type="checkbox" style={{ width: "auto" }} checked={d.motor_activo !== false}
          onChange={(e) => setD({ ...d, motor_activo: e.target.checked })} />
        Esta PC también trabaja (vigila directos, edita y publica)
      </label>
      <label style={{ display: "flex", gap: 8, color: "var(--texto)" }}>
        <input type="checkbox" style={{ width: "auto" }} checked={!!d.iniciar_con_windows}
          onChange={(e) => setD({ ...d, iniciar_con_windows: e.target.checked })} />
        Abrir CLIPPER al prender el PC (en la bandeja)
      </label>
      <div className="fila" style={{ marginTop: 16 }}>
        <button className="btn prim" type="submit">Guardar</button>
        {inicial && <button className="btn" type="button" onClick={() => setModo(null)}>Volver</button>}
        <span className="suave">{msg}</span>
      </div>
      {motor && (
        <p className="suave" style={{ fontSize: 12, marginTop: 14 }}>
          Versión {motor.version} · motor {motor.encendido ? "encendido" : "apagado"} · datos en {motor.carpeta}
        </p>
      )}
    </form>
  );
}
