"use client";
import { Suspense, useEffect, useState } from "react";
import { iniciar } from "@/lib/supabase";
import { local } from "@/lib/local";
import Login from "@/components/Login";
import Panel from "@/components/Panel";
import Configuracion from "@/components/Configuracion";

export default function Inicio() {
  const [conf, setConf] = useState(null);
  const [sesion, setSesion] = useState(undefined);
  const [error, setError] = useState("");

  useEffect(() => {
    local("/api/config").then(setConf).catch((e) => setError(String(e.message || e)));
  }, []);

  useEffect(() => {
    if (!conf?.configurado) return;
    const sb = iniciar(conf.supabase_url, conf.supabase_anon);
    sb.auth.getSession().then(({ data }) => setSesion(data.session));
    const { data } = sb.auth.onAuthStateChange((_e, s) => setSesion(s));
    return () => data.subscription.unsubscribe();
  }, [conf]);

  if (error) return <div className="login caja"><h2>No hay conexión con la app</h2><p className="suave">{error}</p></div>;
  if (!conf) return null;
  if (!conf.configurado) return <Configuracion inicial onListo={() => window.location.reload()} />;
  if (sesion === undefined) return null;
  if (!sesion) return <Login />;
  return (
    <Suspense fallback={null}>
      <Panel sesion={sesion} />
    </Suspense>
  );
}
