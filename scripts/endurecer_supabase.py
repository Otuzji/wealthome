"""Aplica `endurecer_supabase.sql` a la base de `DATABASE_URL` y verifica el resultado.

Uso:  .venv/Scripts/python.exe scripts/endurecer_supabase.py [--solo-auditar]
"""

import sys
from pathlib import Path

import psycopg

RAIZ = Path(__file__).resolve().parent.parent
ROLES_API = ("anon", "authenticated", "service_role")


def leer_database_url():
    for linea in (RAIZ / ".env").read_text().splitlines():
        if linea.startswith("DATABASE_URL="):
            return linea.split("=", 1)[1].strip()
    sys.exit("No hay DATABASE_URL en .env")


def auditar(cur):
    cur.execute(
        """select count(*) from information_schema.role_table_grants
           where table_schema = 'public' and grantee = any(%s)""",
        [list(ROLES_API)],
    )
    grants = cur.fetchone()[0]
    cur.execute(
        "select count(*) filter (where not rowsecurity), count(*) "
        "from pg_tables where schemaname = 'public'"
    )
    sin_rls, total = cur.fetchone()
    # Solo grants DIRECTOS a los roles de la API: el `=U` de PUBLIC sobre el
    # esquema es el default de Postgres, lo usan roles internos de Supabase y
    # sin privilegios sobre tablas no permite leer nada.
    cur.execute(
        """select count(*) from pg_namespace, aclexplode(nspacl) a
           where nspname = 'public' and a.grantee::regrole::text = any(%s)""",
        [list(ROLES_API)],
    )
    usage = cur.fetchone()[0]
    # La prueba definitiva: lo que veria PostgREST actuando como `anon`.
    cur.execute("savepoint prueba; set local role anon")
    try:
        cur.execute("select count(*) from public.accounts_user")
        lectura_anon = f"PERMITIDA ({cur.fetchone()[0]} filas)"
    except psycopg.errors.InsufficientPrivilege:
        lectura_anon = "denegada"
    cur.execute("rollback to savepoint prueba")
    print(f"grants de la API sobre tablas de public   : {grants}")
    print(f"grants directos de la API sobre el esquema: {usage}")
    print(f"tablas de public sin RLS                  : {sin_rls} de {total}")
    print(f"lectura de accounts_user como anon        : {lectura_anon}")
    return grants == 0 and sin_rls == 0 and usage == 0 and lectura_anon == "denegada"


def main():
    solo_auditar = "--solo-auditar" in sys.argv
    with psycopg.connect(leer_database_url(), connect_timeout=15) as cx, cx.cursor() as cur:
        cur.execute("select current_user, current_database()")
        print("conectado como", cur.fetchone())
        if not solo_auditar:
            cur.execute((RAIZ / "scripts" / "endurecer_supabase.sql").read_text())
            print("script aplicado")
        print("--- auditoria ---")
        seguro = auditar(cur)
    print("RESULTADO:", "SEGURO" if seguro else "TODAVIA EXPUESTO")
    sys.exit(0 if seguro else 1)


if __name__ == "__main__":
    main()
