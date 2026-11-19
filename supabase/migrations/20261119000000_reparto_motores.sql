-- Varias PCs con la app abierta: cada canal en vivo lo vigila UNA sola, sin pisarse.
alter table public.fuentes add column if not exists vigilado_por text;
alter table public.fuentes add column if not exists vigilado_hasta timestamptz;

-- Toma (o renueva) el canal para este motor por 90 s. Devuelve true si le toca.
create or replace function public.reclamar_fuente(p_id uuid, p_worker text) returns boolean
language plpgsql security definer set search_path = public as $$
declare ok boolean;
begin
  update public.fuentes
     set vigilado_por = p_worker, vigilado_hasta = now() + interval '90 seconds'
   where id = p_id
     and (vigilado_por is null or vigilado_por = p_worker or vigilado_hasta < now())
  returning true into ok;
  return coalesce(ok, false);
end $$;

create or replace function public.soltar_fuente(p_id uuid, p_worker text) returns void
language sql security definer set search_path = public as $$
  update public.fuentes set vigilado_por = null, vigilado_hasta = null, en_vivo = false
   where id = p_id and vigilado_por = p_worker;
$$;

revoke all on function public.reclamar_fuente(uuid, text) from public, anon, authenticated;
revoke all on function public.soltar_fuente(uuid, text) from public, anon, authenticated;
