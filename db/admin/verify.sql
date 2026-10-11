-- verify.sql: read-only checks. Run as admin on `outageiq`, then paste the output to Claude.
-- Passwords never appear here.

SELECT current_database() AS db, current_user AS who;

SHOW ssl;                      -- expect: on (server SUPPORTS TLS; enforcement is tested by scripts/check_connection.py)

SELECT extname, extversion FROM pg_extension ORDER BY 1;   -- expect: vector

SELECT nspname AS schema, pg_get_userbyid(nspowner) AS owner
FROM pg_namespace WHERE nspname IN ('ops','rag','public');

-- Role attributes: expect all false, and conn limit 5 for the colleague role.
SELECT rolname, rolsuper, rolcreaterole, rolcreatedb, rolconnlimit
FROM pg_roles WHERE rolname LIKE 'outageiq%' ORDER BY 1;

-- Schema privileges per role. Expect indexer: rag only; readers: ops + rag.
SELECT r.rolname,
       has_schema_privilege(r.rolname, 'ops', 'USAGE') AS ops_usage,
       has_schema_privilege(r.rolname, 'rag', 'USAGE') AS rag_usage,
       has_schema_privilege(r.rolname, 'public', 'USAGE') AS public_usage,  -- needed to see the vector type
       has_schema_privilege(r.rolname, 'ops', 'CREATE') AS ops_create,
       has_schema_privilege(r.rolname, 'rag', 'CREATE') AS rag_create
FROM pg_roles r WHERE r.rolname LIKE 'outageiq%' ORDER BY 1;

-- Per-role session settings.
SELECT r.rolname, s.setconfig
FROM pg_db_role_setting s JOIN pg_roles r ON r.oid = s.setrole
WHERE r.rolname LIKE 'outageiq%' ORDER BY 1;

-- Informational: databases the roles can connect to (PUBLIC default makes others true).
SELECT datname, has_database_privilege('outageiq_reader', datname, 'CONNECT') AS reader_can_connect
FROM pg_database WHERE NOT datistemplate ORDER BY 1;
