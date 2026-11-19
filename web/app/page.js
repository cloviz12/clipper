"use client";
import { Suspense, useEffect, useState } from "react";
import { sb } from "@/lib/supabase";
import Login from "@/components/Login";
import Panel from "@/components/Panel";

export default function Inicio() {
  const [sesion, setSesion] = useState(undefined);
  useEffect(() => {
    sb().auth.getSession().then(({ data }) => setSesion(data.session));
    const { data } = sb().auth.onAuthStateChange((_e, s) => setSesion(s));
    return () => data.subscription.unsubscribe();
  }, []);
  if (sesion === undefined) return null;
  if (!sesion) return <Login />;
  return (
    <Suspense fallback={null}>
      <Panel sesion={sesion} />
    </Suspense>
  );
}
