-- TikTok "directo": TikTok exige que una persona confirme cada publicacion (privacidad elegida a mano,
-- interacciones, divulgacion comercial y consentimiento). El motor deja cada clip "esperando" en la columna
-- tiktok; el equipo los confirma en tanda en la pestana TikTok y el motor los publica solos a la hora
-- programada. YouTube e Instagram no cambian: siguen automaticos.
-- Es idempotente: se puede correr mas de una vez.
--
-- clips.tiktok:
--   {"estado":"esperando"}
--   {"estado":"programado","en":"<iso>","post":{privacy_level,title,disable_comment,disable_duet,disable_stitch,
--     brand_content_toggle,brand_organic_toggle},"confirmado_por":"<email>","confirmado_en":"<iso>"}
--   {"estado":"publicando"} | {"estado":"publicado",...} | {"estado":"error","error":"..."}

alter table public.clips add column if not exists tiktok jsonb;
create index if not exists clips_tiktok_idx on public.clips ((tiktok ->> 'estado')) where tiktok is not null;

-- el motor toma UN clip de TikTok cuya hora ya llego, sin que dos motores agarren el mismo
create or replace function public.tomar_tiktok(p_worker text) returns setof public.clips
language plpgsql security definer set search_path = public as $$
declare c public.clips;
begin
  select * into c from public.clips
   where tiktok ->> 'estado' = 'programado' and (tiktok ->> 'en')::timestamptz <= now()
   order by (tiktok ->> 'en')::timestamptz limit 1 for update skip locked;
  if not found then return; end if;
  update public.clips set tiktok = tiktok || jsonb_build_object('estado', 'publicando', 'worker', p_worker)
   where id = c.id returning * into c;
  return next c;
end $$;

revoke all on function public.tomar_tiktok(text) from public, anon, authenticated;
grant execute on function public.tomar_tiktok(text) to service_role;
