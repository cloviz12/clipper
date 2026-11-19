// Habla con la app de escritorio (servidor local en 127.0.0.1). El encabezado evita que
// cualquier pagina web abierta en el navegador pueda mandarle ordenes a la app.
export async function local(ruta, datos) {
  const r = await fetch(ruta, {
    method: datos === undefined ? "GET" : "POST",
    headers: { "X-Clipper": "1", "Content-Type": "application/json" },
    body: datos === undefined ? undefined : JSON.stringify(datos),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || `Error ${r.status}`);
  return j;
}
