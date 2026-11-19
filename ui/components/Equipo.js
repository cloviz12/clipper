"use client";
import { useEffect, useState } from "react";
import { sb } from "@/lib/supabase";
import { local } from "@/lib/local";
import { crearCodigo } from "@/lib/invitacion";

export default function Equipo({ email }) {
  const [lista, setLista] = useState([]);
  const [nuevo, setNuevo] = useState("");
  const [codigo, setCodigo] = useState("");
  const [copiado, setCopiado] = useState(false);
  const cargar = () => sb().from("miembros").select("*").order("creado").then(({ data }) => setLista(data || []));
  useEffect(() => {
    cargar();
    local("/api/config").then((c) => c.supabase_url && setCodigo(crearCodigo(c.supabase_url, c.supabase_anon))).catch(() => {});
  }, []);
  async function copiar() {
    try {
      await navigator.clipboard.writeText(codigo);
    } catch {
      const t = document.getElementById("codigo-invitacion");
      t.select();
      document.execCommand("copy");
    }
    setCopiado(true);
    setTimeout(() => setCopiado(false), 2500);
  }
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
      <p className="suave" style={{ marginTop: 0 }}>
        Para invitar a alguien: 1) agrega su correo aquí abajo, 2) mándale el código de invitación. Él instala CLIPPER,
        elige <b>Me invitaron</b>, pega el código y crea su cuenta con ese correo. No tiene que llenar ninguna llave:
        recibe las tuyas al entrar.
      </p>
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
      {codigo && (
        <div style={{ marginTop: 18 }}>
          <label>Código de invitación</label>
          <textarea id="codigo-invitacion" readOnly value={codigo} rows={3} style={{ width: "100%", fontFamily: "monospace", fontSize: 12 }}
            onFocus={(e) => e.target.select()} />
          <div className="fila" style={{ marginTop: 8 }}>
            <button className="btn" type="button" onClick={copiar}>{copiado ? "¡Copiado!" : "Copiar código"}</button>
            <span className="suave" style={{ fontSize: 12 }}>
              No lleva llaves secretas: aunque alguien más lo vea, solo entra quien esté en esta lista.
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
