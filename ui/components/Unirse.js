"use client";
import { useEffect, useState } from "react";
import { sb } from "@/lib/supabase";
import { local } from "@/lib/local";

// PC invitada, ya con sesion: baja las llaves que el dueno dejo en el equipo y reinicia la app.
export default function Unirse({ sesion }) {
  const [msg, setMsg] = useState("Recibiendo la configuración de tu equipo...");
  const [error, setError] = useState(false);
  async function intentar() {
    setError(false);
    setMsg("Recibiendo la configuración de tu equipo...");
    try {
      await local("/api/unirse", { token: sesion.access_token });
      setMsg("¡Listo! CLIPPER se reinicia con todo configurado.");
    } catch (e) {
      setError(true);
      setMsg(String(e.message || e));
    }
  }
  useEffect(() => { intentar(); }, []);
  return (
    <div className="login caja">
      <div className="logo" style={{ marginBottom: 14 }}>CLIP<span>PER</span></div>
      <h2>Unirse al equipo</h2>
      <p className={error ? "" : "suave"}>{msg}</p>
      <p className="suave" style={{ fontSize: 12 }}>Entraste como {sesion.user?.email}.</p>
      {error && (
        <div className="fila" style={{ marginTop: 12 }}>
          <button className="btn prim" onClick={intentar}>Intentar de nuevo</button>
          <button className="btn" onClick={() => sb().auth.signOut()}>Entrar con otro correo</button>
        </div>
      )}
    </div>
  );
}
