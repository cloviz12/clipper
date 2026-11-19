// Codigo de invitacion: solo lleva la direccion del proyecto y la llave PUBLICA de Supabase.
// Las llaves secretas nunca van en el codigo: la app del invitado las recibe despues de iniciar
// sesion, y solo si su correo esta en Equipo.
const PREFIJO = "CLIPPER-";

export function crearCodigo(url, anon) {
  const b = btoa(JSON.stringify({ u: url, k: anon }));
  return PREFIJO + b.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function leerCodigo(codigo) {
  const limpio = (codigo || "").replace(/\s+/g, "");
  if (!limpio.startsWith(PREFIJO)) throw new Error("Ese no es un código de CLIPPER. Debe empezar con CLIPPER-");
  let b = limpio.slice(PREFIJO.length).replace(/-/g, "+").replace(/_/g, "/");
  while (b.length % 4) b += "=";
  let d;
  try {
    d = JSON.parse(atob(b));
  } catch {
    throw new Error("El código está incompleto. Cópialo otra vez completo.");
  }
  if (!d.u || !d.k) throw new Error("El código está incompleto. Cópialo otra vez completo.");
  return { supabase_url: d.u, supabase_anon: d.k };
}
