import { createClient } from "@supabase/supabase-js";

let cliente = null;
export function iniciar(url, llave) {
  if (!cliente) cliente = createClient(url, llave, { auth: { persistSession: true, autoRefreshToken: true } });
  return cliente;
}
export function sb() {
  if (!cliente) throw new Error("Supabase sin configurar");
  return cliente;
}

export const PLATAFORMAS = [
  { id: "youtube", nombre: "YouTube Shorts" },
  { id: "tiktok", nombre: "TikTok" },
  { id: "instagram", nombre: "Instagram Reels" },
];

export function hace(fecha) {
  if (!fecha) return "";
  const s = Math.max(0, (Date.now() - new Date(fecha).getTime()) / 1000);
  if (s < 60) return `hace ${Math.round(s)} s`;
  if (s < 3600) return `hace ${Math.round(s / 60)} min`;
  if (s < 86400) return `hace ${Math.round(s / 3600)} h`;
  return new Date(fecha).toLocaleString("es-CO", { dateStyle: "short", timeStyle: "short" });
}
