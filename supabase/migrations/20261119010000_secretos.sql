-- Secretos compartidos entre las apps (por ejemplo el token de GitHub para las actualizaciones).
-- Sin politicas: solo las apps (con la llave service_role) los leen; el navegador nunca.
create table if not exists public.secretos (
  clave text primary key,
  valor text not null,
  actualizado timestamptz not null default now()
);
alter table public.secretos enable row level security;
