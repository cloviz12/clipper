-- Llaves compartidas del equipo (Supabase secreta, Claude, Google, TikTok).
-- El dueno las llena UNA vez en su PC y su app las guarda aqui. Un companero invitado solo pega el
-- codigo de invitacion, entra con su correo (agregado en Equipo) y su app las baja de aqui.
-- La tabla queda cerrada: solo se leen con la funcion de abajo, y solo si el correo esta en miembros.
-- Es idempotente: se puede correr mas de una vez.

create table if not exists public.config_equipo (
  id int primary key default 1 check (id = 1),
  datos jsonb not null default '{}'::jsonb,
  actualizado timestamptz not null default now()
);
alter table public.config_equipo enable row level security;   -- sin politicas: el navegador no la ve

create or replace function public.config_del_equipo() returns jsonb
language sql stable security definer set search_path = public as $$
  select case when public.es_miembro()
    then coalesce((select datos from public.config_equipo where id = 1), '{}'::jsonb) end;
$$;

revoke all on function public.config_del_equipo() from public, anon;
grant execute on function public.config_del_equipo() to authenticated;
grant all on public.config_equipo to service_role;
