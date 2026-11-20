"use client";
import { useEffect, useState } from "react";
import { sb } from "@/lib/supabase";

export default function Registro() {
  const [ev, setEv] = useState([]);
  useEffect(() => {
    sb().from("eventos").select("*").order("id", { ascending: false }).limit(200).then(({ data }) => setEv(data || []));
    const ch = sb().channel("eventos").on("postgres_changes", { event: "INSERT", schema: "public", table: "eventos" },
      (p) => setEv((x) => [p.new, ...x].slice(0, 300))).subscribe();
    return () => sb().removeChannel(ch);
  }, []);
  return (
    <div className="caja log">
      {ev.length === 0 && <div className="suave">Sin actividad todavía.</div>}
      {ev.map((e) => (
        <div key={e.id} className={e.nivel}>
          <span className="suave">{new Date(e.creado).toLocaleTimeString("es-CO")}</span>
          {e.datos?.worker && <span className="suave"> [{e.datos.worker}]</span>} {e.mensaje}
        </div>
      ))}
    </div>
  );
}
