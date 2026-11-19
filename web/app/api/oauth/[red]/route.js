import { NextResponse } from "next/server";
import { miembroDesdeToken } from "@/lib/servidor";
import { REDES, redirectDe } from "@/lib/redes";

export async function GET(req, { params }) {
  const { red } = await params;
  const conf = REDES[red];
  if (!conf) return new NextResponse("Red desconocida", { status: 404 });
  const token = new URL(req.url).searchParams.get("token");
  const email = await miembroDesdeToken(token);
  if (!email) return new NextResponse("Solo los miembros del equipo pueden conectar cuentas", { status: 403 });
  const state = crypto.randomUUID();
  const res = NextResponse.redirect(conf.autorizar({ redirect: redirectDe(req, red), state }));
  res.cookies.set("oauth_estado", `${red}:${state}`, { httpOnly: true, secure: true, sameSite: "lax", maxAge: 600, path: "/" });
  return res;
}
