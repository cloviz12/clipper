"use client";
import { useEffect, useState } from "react";
import { local } from "@/lib/local";

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
  return (
    <form className={inicial ? "login caja" : "caja"} style={{ maxWidth: 640 }} onSubmit={guardar}>
      {inicial && <div className="logo" style={{ marginBottom: 6 }}>CLIP<span>PER</span></div>}
      <h2>{inicial ? "Configurar esta PC" : "Esta PC"}</h2>
      <p className="suave" style={{ marginTop: 0 }}>
        Los dos usan el mismo proyecto de Supabase para ver los mismos clips. Estos datos se guardan solo en esta computadora.
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
