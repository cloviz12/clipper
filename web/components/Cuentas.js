"use client";
import { useEffect, useState } from "react";
import { sb, hace, PLATAFORMAS } from "@/lib/supabase";

const NOTAS = {
  youtube: "Mientras Google no apruebe la app (auditoría de la API de YouTube), los videos subidos por API quedan privados.",
  tiktok: "Sin la auditoría de TikTok solo se puede publicar privado; por eso el modo 'borrador' los manda a la bandeja de la app para publicarlos con un toque.",
  instagram: "Necesita una cuenta profesional (creador o empresa).",
};

export default function Cuentas({ sesion }) {
  const [cuentas, setCuentas] = useState([]);
  useEffect(() => { sb().rpc("estado_cuentas").then(({ data }) => setCuentas(data || [])); }, []);
  const conectar = (red) => { window.location.href = `/api/oauth/${red}?token=${encodeURIComponent(sesion.access_token)}`; };
  return (
    <div className="grid">
      {PLATAFORMAS.map((p) => {
        const c = cuentas.find((x) => x.plataforma === p.id);
        return (
          <div key={p.id} className="caja">
            <h3>{p.nombre}</h3>
            {c ? <p><span className="chip ok">conectado</span> {c.cuenta} <span className="suave">· {hace(c.conectado)}</span></p>
              : <p><span className="chip">sin conectar</span></p>}
            <p className="suave" style={{ fontSize: 12 }}>{NOTAS[p.id]}</p>
            <button className="btn prim" onClick={() => conectar(p.id)}>{c ? "Volver a conectar" : "Conectar"}</button>
          </div>
        );
      })}
    </div>
  );
}
