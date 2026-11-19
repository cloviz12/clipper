"use client";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { sb, hace } from "@/lib/supabase";
import Clips from "./Clips";
import EnVivo from "./EnVivo";
import Pedidos from "./Pedidos";
import Cuentas from "./Cuentas";
import Sonidos from "./Sonidos";
import Ajustes from "./Ajustes";
import Equipo from "./Equipo";
import Registro from "./Registro";

const PESTANAS = [
  ["clips", "Clips"], ["vivo", "En vivo"], ["pedidos", "Pedidos"], ["cuentas", "Cuentas"],
  ["sonidos", "Sonidos"], ["ajustes", "Ajustes"], ["equipo", "Equipo"], ["registro", "Registro"],
];

function pitido() {
  try {
    const ctx = new AudioContext();
    [0, 0.12].forEach((t, i) => {
      const o = ctx.createOscillator(), g = ctx.createGain();
      o.frequency.value = i ? 1320 : 880;
      g.gain.setValueAtTime(0.15, ctx.currentTime + t);
      g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + t + 0.18);
      o.connect(g).connect(ctx.destination);
      o.start(ctx.currentTime + t);
      o.stop(ctx.currentTime + t + 0.2);
    });
  } catch {}
}

export default function Panel({ sesion }) {
  const params = useSearchParams();
  const [pestana, setPestana] = useState(params.get("pestana") || "clips");
  const [aviso, setAviso] = useState(params.get("aviso") || "");
  const [miembro, setMiembro] = useState(null);
  const [workers, setWorkers] = useState([]);
  const [porRevisar, setPorRevisar] = useState(0);
  const [, tic] = useState(0);
  const avisar = useRef(false);

  useEffect(() => {
    sb().rpc("es_miembro").then(({ data }) => setMiembro(!!data));
    const cargarW = () => sb().from("workers").select("*").then(({ data }) => setWorkers(data || []));
    const contar = () => sb().from("clips").select("id", { count: "exact", head: true }).eq("estado", "revisar")
      .then(({ count }) => setPorRevisar(count || 0));
    cargarW();
    contar();
    if (typeof Notification !== "undefined" && Notification.permission === "default") Notification.requestPermission();
    const ch = sb().channel("panel")
      .on("postgres_changes", { event: "*", schema: "public", table: "workers" }, cargarW)
      .on("postgres_changes", { event: "*", schema: "public", table: "clips" }, (p) => {
        contar();
        if (p.eventType === "INSERT" && avisar.current) {
          pitido();
          const c = p.new;
          if (typeof Notification !== "undefined" && Notification.permission === "granted") {
            new Notification(c.estado === "aprobado" ? `Publicando ya: ${c.canal}` : `Clip nuevo de ${c.canal}`, { body: c.hook || c.titulo || "" });
          }
        }
      })
      .subscribe();
    const t = setTimeout(() => (avisar.current = true), 3000);
    const i = setInterval(() => tic((x) => x + 1), 10000);
    return () => { sb().removeChannel(ch); clearTimeout(t); clearInterval(i); };
  }, []);

  if (miembro === false) {
    return (
      <div className="login caja">
        <h2>Tu correo no está en el equipo</h2>
        <p className="suave">Pídele a tu compañero que te agregue en la pestaña Equipo con {sesion.user.email}.</p>
        <button className="btn" onClick={() => sb().auth.signOut()}>Salir</button>
      </div>
    );
  }

  const vivos = workers.filter((w) => Date.now() - new Date(w.visto).getTime() < 60000);
  const enVivo = vivos.flatMap((w) => w.estado?.en_vivo || []);
  const cola = vivos.reduce((a, w) => a + (w.estado?.cola || 0), 0);
  const editando = vivos.map((w) => w.estado?.editando).filter(Boolean);

  return (
    <>
      <div className="top">
        <div className="logo">CLIP<span>PER</span></div>
        <div className="tabs">
          {PESTANAS.map(([id, nom]) => (
            <button key={id} className={`tab ${pestana === id ? "on" : ""}`} onClick={() => setPestana(id)}>
              {nom}{id === "clips" && porRevisar > 0 && <span className="num">{porRevisar}</span>}
            </button>
          ))}
        </div>
        <div className="motor">
          <span className={`punto ${enVivo.length ? "vivo" : vivos.length ? "ok" : ""}`} />
          {vivos.length
            ? <>Motor encendido{enVivo.length ? ` · en vivo: ${enVivo.join(", ")}` : ""}{editando.length ? ` · editando ${editando.join(", ")}` : ""}{cola ? ` · ${cola} en cola` : ""}</>
            : <>Motor apagado{workers[0] ? ` (visto ${hace(workers[0].visto)})` : ""}</>}
          <button className="btn chico" onClick={() => sb().auth.signOut()}>Salir</button>
        </div>
      </div>
      <main>
        {aviso && <div className="aviso-top" onClick={() => setAviso("")}>{aviso}</div>}
        {pestana === "clips" && <Clips email={sesion.user.email} />}
        {pestana === "vivo" && <EnVivo email={sesion.user.email} />}
        {pestana === "pedidos" && <Pedidos email={sesion.user.email} />}
        {pestana === "cuentas" && <Cuentas sesion={sesion} />}
        {pestana === "sonidos" && <Sonidos />}
        {pestana === "ajustes" && <Ajustes />}
        {pestana === "equipo" && <Equipo email={sesion.user.email} />}
        {pestana === "registro" && <Registro />}
      </main>
    </>
  );
}
