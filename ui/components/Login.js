"use client";
import { useState } from "react";
import { sb } from "@/lib/supabase";

export default function Login({ invitado }) {
  const [email, setEmail] = useState("");
  const [clave, setClave] = useState("");
  const [modo, setModo] = useState(invitado ? "crear" : "entrar");
  const [msg, setMsg] = useState("");
  async function enviar(e) {
    e.preventDefault();
    setMsg("");
    const f = modo === "entrar" ? sb().auth.signInWithPassword : sb().auth.signUp;
    const { error, data } = await f.call(sb().auth, { email, password: clave });
    if (error) setMsg(error.message);
    else if (modo === "crear" && !data.session) setMsg("Revisa tu correo para confirmar la cuenta y luego entra.");
  }
  return (
    <div className="login caja">
      <div className="logo" style={{ marginBottom: 14 }}>CLIP<span>PER</span></div>
      {invitado && (
        <p className="suave" style={{ marginTop: 0 }}>
          Usa el mismo correo que tu compañero agregó en <b>Equipo</b>. Si es tu primera vez, crea tu cuenta;
          al entrar, CLIPPER recibe solo todo lo demás.
        </p>
      )}
      <form onSubmit={enviar}>
        <label>Correo</label>
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        <label>Contraseña</label>
        <input type="password" value={clave} onChange={(e) => setClave(e.target.value)} required minLength={6} />
        <div className="fila" style={{ marginTop: 16 }}>
          <button className="btn prim" type="submit">{modo === "entrar" ? "Entrar" : "Crear cuenta"}</button>
          <button className="btn" type="button" onClick={() => setModo(modo === "entrar" ? "crear" : "entrar")}>
            {modo === "entrar" ? "Crear cuenta" : "Ya tengo cuenta"}
          </button>
        </div>
        {msg && <p className="suave">{msg}</p>}
        <p className="suave" style={{ fontSize: 12 }}>Solo los correos del equipo pueden ver el panel. La primera cuenta creada queda como dueña.</p>
      </form>
    </div>
  );
}
