import { createClient } from "@supabase/supabase-js";

export function admin() {
  return createClient(process.env.NEXT_PUBLIC_SUPABASE_URL, process.env.SUPABASE_SERVICE_ROLE_KEY, {
    auth: { persistSession: false },
  });
}

/** Devuelve el correo si el token es de un miembro del equipo; si no, null. */
export async function miembroDesdeToken(token) {
  if (!token) return null;
  const db = admin();
  const { data } = await db.auth.getUser(token);
  const email = data?.user?.email?.toLowerCase();
  if (!email) return null;
  const { data: m } = await db.from("miembros").select("email").eq("email", email).maybeSingle();
  return m ? email : null;
}
