"use client";
import { useEffect, useState } from "react";
import { sb } from "@/lib/supabase";

export default function Equipo({ email }) {
  const [lista, setLista] = useState([]);
  const [nuevo, setNuevo] = useState("");
  const cargar = () => sb().from("miembros").select("*").order("creado").then(({ data }) => setLista(data || []));
  useEffect(() => { cargar(); }, []);
  async function agregar(e) {
    e.preventDefault();
    const { error } = await sb().from("miembros").insert({ email: nuevo.trim().toLowerCase() });
    if (error) alert(error.message);
    setNuevo("");
    cargar();
  }
  return (
    <div className="caja" style={{ maxWidth: 560 }}>
      <h2>Equipo</h2>
      <p className="suave" style={{ marginTop: 0 }}>Agrega el correo de tu compañero; luego él crea su cuenta con ese correo en la pantalla de entrada.</p>
      <div className="lista">
        {lista.map((m) => (
          <div key={m.email} className="fila">
            <span style={{ flex: 1 }}>{m.email}{m.email === email.toLowerCase() && <span className="suave"> (tú)</span>}</span>
            {m.email !== email.toLowerCase() && (
              <button className="btn chico peligro" onClick={() => sb().from("miembros").delete().eq("email", m.email).then(cargar)}>Quitar</button>
            )}
          </div>
        ))}
      </div>
      <form className="fila" onSubmit={agregar} style={{ marginTop: 12 }}>
        <input type="email" placeholder="correo@ejemplo.com" value={nuevo} onChange={(e) => setNuevo(e.target.value)} required style={{ flex: 1 }} />
        <button className="btn prim">Agregar</button>
      </form>
    </div>
  );
}
