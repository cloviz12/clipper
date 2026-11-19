"use client";
import { useEffect, useState } from "react";
import { sb, hace, PLATAFORMAS } from "@/lib/supabase";
import { local } from "@/lib/local";

const NOTAS = {
  youtube: "Se abre tu navegador para entrar con la cuenta del canal. Mientras Google no apruebe la app, lo que se sube por la API queda privado.",
  tiktok: "Se abre tu navegador para autorizar. Sin la auditoría de TikTok llega como borrador a la bandeja de la app.",
  instagram: "Cuenta profesional. Pega el token que genera Meta (app > Instagram > Generar token).",
};

export default function Cuentas({ sesion }) {
  const [cuentas, setCuentas] = useState([]);
  const [msg, setMsg] = useState("");
  const [igToken, setIgToken] = useState("");
  const cargar = () => sb().rpc("estado_cuentas").then(({ data }) => setCuentas(data || []));
  useEffect(() => { cargar(); const i = setInterval(cargar, 4000); return () => clearInterval(i); }, []);
  async function conectar(red) {
    setMsg("");
    try {
      await local(`/api/oauth/${red}`, { token: sesion.access_token });
      setMsg("Se abrió tu navegador: autoriza y vuelve aquí. Se actualiza solo.");
    } catch (e) { setMsg(String(e.message || e)); }
  }
  async function instagram(e) {
    e.preventDefault();
    try {
      const r = await local("/api/instagram", { token: sesion.access_token, ig_token: igToken.trim() });
      setMsg(`Instagram conectado: ${r.cuenta}`);
      setIgToken("");
      cargar();
    } catch (err) { setMsg(String(err.message || err)); }
  }
  return (
    <>
      {msg && <div className="aviso-top" onClick={() => setMsg("")}>{msg}</div>}
      <div className="grid">
        {PLATAFORMAS.map((p) => {
          const c = cuentas.find((x) => x.plataforma === p.id);
          return (
            <div key={p.id} className="caja">
              <h3>{p.nombre}</h3>
              {c ? <p><span className="chip ok">conectado</span> {c.cuenta} <span className="suave">· {hace(c.conectado)}</span></p>
                : <p><span className="chip">sin conectar</span></p>}
              <p className="suave" style={{ fontSize: 12 }}>{NOTAS[p.id]}</p>
              {p.id === "instagram" ? (
                <form className="fila" onSubmit={instagram}>
                  <input type="password" placeholder="Token de Instagram" value={igToken} onChange={(e) => setIgToken(e.target.value)} required style={{ flex: 1 }} />
                  <button className="btn prim">{c ? "Cambiar" : "Conectar"}</button>
                </form>
              ) : (
                <button className="btn prim" onClick={() => conectar(p.id)}>{c ? "Volver a conectar" : "Conectar"}</button>
              )}
            </div>
          );
        })}
      </div>
    </>
  );
}
