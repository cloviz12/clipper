-- Los proyectos nuevos de Supabase ya no dan permisos automaticos sobre el esquema public.
-- Sin esto el motor (llave secreta = rol service_role) falla con "permission denied" (42501).
-- Es idempotente: se puede correr mas de una vez.

-- Motor: acceso total a lo del esquema public
grant usage on schema public to service_role;
grant all on all tables in schema public to service_role;
grant all on all sequences in schema public to service_role;
grant execute on all functions in schema public to service_role;

-- App (usuarios con sesion iniciada): solo lo que las politicas RLS ya permiten.
-- "cuentas" (tokens de las redes) queda cerrada para el navegador.
grant usage on schema public to authenticated;
grant select, insert, delete on public.miembros to authenticated;
grant select, insert, update, delete on public.fuentes, public.trabajos, public.clips to authenticated;
grant select, update on public.ajustes to authenticated;
grant select on public.eventos, public.workers to authenticated;
grant usage, select on all sequences in schema public to authenticated;

-- Tablas y funciones que se creen despues
alter default privileges in schema public grant all on tables to service_role;
alter default privileges in schema public grant all on sequences to service_role;
alter default privileges in schema public grant execute on functions to service_role;
