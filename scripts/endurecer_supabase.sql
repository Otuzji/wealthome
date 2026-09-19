-- Endurece el esquema `public` de Supabase para una app Django.
--
-- Contexto: Wealthome habla con Postgres directamente (rol `postgres`, que
-- tiene BYPASSRLS) y NUNCA usa la Data API (PostgREST) ni el cliente JS de
-- Supabase. Sin embargo, Supabase concede por defecto TODOS los privilegios a
-- los roles de la API (`anon`, `authenticated`, `service_role`) sobre cuanto se
-- crea en `public`, y ahi es donde Django crea sus tablas. Resultado: cualquiera
-- con la clave `anon` (publica por diseno) podia leer y borrar `accounts_user`,
-- `django_session`, `households_invitation`, etc. Este script cierra eso.
--
-- Como aplicarlo (idempotente, se puede repetir):
--   .venv/Scripts/python.exe scripts/endurecer_supabase.py
-- o pegarlo en el SQL Editor del panel de Supabase.
--
-- Ademas, en el panel: Project Settings -> Data API -> desactivar
-- "Enable Data API" (o quitar `public` de "Exposed schemas"). Eso no se puede
-- hacer por SQL.

begin;

-- 1. Quitar lo ya concedido sobre lo que existe hoy.
revoke all on all tables    in schema public from anon, authenticated, service_role;
revoke all on all sequences in schema public from anon, authenticated, service_role;
revoke all on all functions in schema public from anon, authenticated, service_role;
revoke usage on schema public from anon, authenticated, service_role;

-- 2. Que las tablas que creen futuras migraciones de Django (como `postgres`)
--    nazcan sin esos privilegios; si no, la proxima migracion reabre el hueco.
alter default privileges for role postgres in schema public
    revoke all on tables    from anon, authenticated, service_role;
alter default privileges for role postgres in schema public
    revoke all on sequences from anon, authenticated, service_role;
alter default privileges for role postgres in schema public
    revoke all on functions from anon, authenticated, service_role;

-- 3. RLS en todas las tablas de `public`: defensa en profundidad y silencia el
--    linter de Supabase. Django no se ve afectado: `postgres` tiene BYPASSRLS y
--    ademas es el dueno de las tablas.
do $$
declare t record;
begin
    for t in select tablename from pg_tables where schemaname = 'public' loop
        execute format('alter table public.%I enable row level security', t.tablename);
    end loop;
end $$;

commit;
