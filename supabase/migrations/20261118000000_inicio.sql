-- CLIPPER: esquema inicial. Solo los correos en "miembros" ven y manejan el sistema.
-- El primer usuario que se registre queda como miembro automaticamente; desde el panel agrega al companero.

create extension if not exists pgcrypto;

create table public.miembros (
  email text primary key,
  nombre text,
  creado timestamptz not null default now()
);

create or replace function public.es_miembro() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.miembros m where lower(m.email) = lower(coalesce(auth.jwt() ->> 'email', '')));
$$;

-- primer registro = primer miembro
create or replace function public.primer_miembro() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if not exists (select 1 from public.miembros) then
    insert into public.miembros (email) values (lower(new.email));
  end if;
  return new;
end $$;
create trigger al_registrarse after insert on auth.users for each row execute function public.primer_miembro();

-- canales que se vigilan
create table public.fuentes (
  id uuid primary key default gen_random_uuid(),
  url text not null,
  nombre text,
  plataforma text,                                   -- twitch | kick | youtube
  modo text not null default 'en_vivo' check (modo in ('en_vivo', 'destacados', 'videos')),
  publicacion text not null default 'revisar' check (publicacion in ('auto', 'revisar')),
  activo boolean not null default true,
  sensibilidad real not null default 1.0,            -- 0.5 = mas clips, 2 = solo picos enormes
  plataformas text[] not null default '{youtube,tiktok,instagram}',
  opciones jsonb not null default '{}'::jsonb,
  en_vivo boolean not null default false,
  titulo_directo text,
  ultimo_chequeo timestamptz,
  creado timestamptz not null default now(),
  creado_por text
);

-- pedidos sueltos (un link, un VOD, un canal)
create table public.trabajos (
  id uuid primary key default gen_random_uuid(),
  url text not null,
  clips int not null default 3,
  duracion text not null default '20-45',
  opciones jsonb not null default '{}'::jsonb,
  estado text not null default 'pendiente' check (estado in ('pendiente', 'procesando', 'terminado', 'error')),
  progreso text,
  error text,
  worker text,
  creado timestamptz not null default now(),
  creado_por text,
  iniciado timestamptz,
  terminado timestamptz
);

create table public.clips (
  id uuid primary key default gen_random_uuid(),
  fuente_id uuid references public.fuentes(id) on delete set null,
  trabajo_id uuid references public.trabajos(id) on delete set null,
  canal text,
  origen text,                                       -- en_vivo | clip_twitch | clip_kick | vod | video
  url_fuente text,
  inicio real,
  duracion real,
  puntaje real,
  senales text[],
  transcripcion text,
  hook text,
  titulo text,
  descripcion text,
  textos jsonb not null default '{}'::jsonb,         -- caption por plataforma
  hashtags text[],
  ia jsonb not null default '{}'::jsonb,             -- veredicto de la IA (sirve solo, razon)
  video_path text,
  miniatura_path text,
  estado text not null default 'revisar'
    check (estado in ('procesando', 'revisar', 'aprobado', 'programado', 'publicando', 'publicado', 'descartado', 'error')),
  publicar_en timestamptz,
  plataformas text[] not null default '{youtube,tiktok,instagram}',
  publicaciones jsonb not null default '{}'::jsonb,
  errores jsonb not null default '{}'::jsonb,
  detectado_en timestamptz,
  aprobado_por text,
  creado timestamptz not null default now()
);
create index clips_estado_idx on public.clips (estado, creado desc);

create table public.eventos (
  id bigserial primary key,
  nivel text not null default 'info',
  mensaje text not null,
  datos jsonb,
  creado timestamptz not null default now()
);
create index eventos_creado_idx on public.eventos (creado desc);

create table public.workers (
  nombre text primary key,
  visto timestamptz not null default now(),
  version text,
  estado jsonb
);

create table public.ajustes (
  id int primary key default 1 check (id = 1),
  datos jsonb not null default '{}'::jsonb,
  actualizado timestamptz not null default now()
);
insert into public.ajustes (id, datos) values (1, '{
  "duracion_clip": "20-45",
  "idioma": "es",
  "whisper_modelo": "small",
  "formato": "auto",
  "efectos_camara": "medio",
  "efectos_sonido": "medio",
  "hook_en_pantalla": true,
  "mostrar_credito": true,
  "mayusculas": true,
  "auto_puntaje_minimo": 70,
  "hashtags_base": ["#clips", "#streamer", "#viral", "#parati"],
  "horarios": [],
  "tiktok_modo": "borrador",
  "youtube_privacidad": "public",
  "youtube_categoria": "20",
  "ia_modelo": "claude-haiku-5-5",
  "dias_guardar_videos": 3
}'::jsonb);

-- tokens de las redes: solo el motor (service role) y las rutas del servidor los leen
create table public.cuentas (
  plataforma text primary key check (plataforma in ('youtube', 'tiktok', 'instagram')),
  cuenta text,
  datos jsonb not null default '{}'::jsonb,
  conectado timestamptz not null default now()
);

create or replace function public.estado_cuentas()
returns table (plataforma text, cuenta text, conectado timestamptz)
language sql stable security definer set search_path = public as $$
  select c.plataforma, c.cuenta, c.conectado from public.cuentas c where public.es_miembro();
$$;

-- el motor toma pedidos sin que dos motores agarren el mismo
create or replace function public.tomar_trabajo(p_worker text) returns setof public.trabajos
language plpgsql security definer set search_path = public as $$
declare t public.trabajos;
begin
  select * into t from public.trabajos where estado = 'pendiente' order by creado limit 1 for update skip locked;
  if not found then return; end if;
  update public.trabajos set estado = 'procesando', worker = p_worker, iniciado = now() where id = t.id returning * into t;
  return next t;
end $$;

create or replace function public.tomar_clip_para_publicar(p_worker text) returns setof public.clips
language plpgsql security definer set search_path = public as $$
declare c public.clips;
begin
  select * into c from public.clips
   where estado = 'aprobado' or (estado = 'programado' and publicar_en <= now())
   order by coalesce(publicar_en, creado) limit 1 for update skip locked;
  if not found then return; end if;
  update public.clips set estado = 'publicando' where id = c.id returning * into c;
  return next c;
end $$;

revoke all on function public.tomar_trabajo(text) from public, anon, authenticated;
revoke all on function public.tomar_clip_para_publicar(text) from public, anon, authenticated;
revoke all on function public.primer_miembro() from public, anon, authenticated;
revoke all on function public.estado_cuentas() from public, anon;
grant execute on function public.estado_cuentas() to authenticated;

-- ===================== seguridad por filas
alter table public.miembros enable row level security;
alter table public.fuentes enable row level security;
alter table public.trabajos enable row level security;
alter table public.clips enable row level security;
alter table public.eventos enable row level security;
alter table public.workers enable row level security;
alter table public.ajustes enable row level security;
alter table public.cuentas enable row level security;   -- sin politicas: nadie desde el navegador

create policy miembros_ver on public.miembros for select to authenticated using ((select public.es_miembro()));
create policy miembros_agregar on public.miembros for insert to authenticated with check ((select public.es_miembro()));
create policy miembros_quitar on public.miembros for delete to authenticated using ((select public.es_miembro()));

create policy fuentes_todo on public.fuentes for all to authenticated using ((select public.es_miembro())) with check ((select public.es_miembro()));
create policy trabajos_todo on public.trabajos for all to authenticated using ((select public.es_miembro())) with check ((select public.es_miembro()));
create policy clips_todo on public.clips for all to authenticated using ((select public.es_miembro())) with check ((select public.es_miembro()));
create policy ajustes_ver on public.ajustes for select to authenticated using ((select public.es_miembro()));
create policy ajustes_cambiar on public.ajustes for update to authenticated using ((select public.es_miembro())) with check ((select public.es_miembro()));
create policy eventos_ver on public.eventos for select to authenticated using ((select public.es_miembro()));
create policy workers_ver on public.workers for select to authenticated using ((select public.es_miembro()));

-- ===================== tiempo real para el panel
alter publication supabase_realtime add table public.clips, public.trabajos, public.fuentes, public.eventos, public.workers;

-- ===================== archivos: videos de clips y libreria de efectos de sonido
insert into storage.buckets (id, name, public, file_size_limit)
values ('clips', 'clips', false, 52428800), ('sfx', 'sfx', false, 10485760)
on conflict (id) do nothing;

create policy archivos_ver on storage.objects for select to authenticated
  using (bucket_id in ('clips', 'sfx') and (select public.es_miembro()));
create policy archivos_subir on storage.objects for insert to authenticated
  with check (bucket_id = 'sfx' and (select public.es_miembro()));
create policy archivos_borrar on storage.objects for delete to authenticated
  using (bucket_id in ('clips', 'sfx') and (select public.es_miembro()));
