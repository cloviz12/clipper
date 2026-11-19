import { NextResponse } from "next/server";
import { admin } from "@/lib/servidor";
import { REDES, redirectDe } from "@/lib/redes";

export async function GET(req, { params }) {
  const { red } = await params;
  const url = new URL(req.url);
  const volver = (msg) => NextResponse.redirect(`${new URL(req.url).origin}/?pestana=cuentas&aviso=${encodeURIComponent(msg)}`);
  const esperado = req.cookies.get("oauth_estado")?.value;
  if (!REDES[red] || esperado !== `${red}:${url.searchParams.get("state")}`) return volver("La conexion vencio, intenta otra vez");
  if (url.searchParams.get("error")) return volver(`${red}: ${url.searchParams.get("error_description") || url.searchParams.get("error")}`);
  try {
    const { cuenta, datos } = await REDES[red].canjear(url.searchParams.get("code"), redirectDe(req, red));
    const { error } = await admin().from("cuentas").upsert({ plataforma: red, cuenta, datos, conectado: new Date().toISOString() });
    if (error) throw error;
    const res = volver(`${red} conectado: ${cuenta}`);
    res.cookies.delete("oauth_estado");
    return res;
  } catch (e) {
    return volver(`${red}: ${String(e.message || e).slice(0, 200)}`);
  }
}
