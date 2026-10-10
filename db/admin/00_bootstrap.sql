-- 00_bootstrap.sql
-- Run ONCE as your RDS admin user, connected to the `postgres` database.
-- Creates this project's database and its own login role. Touches nothing else.
-- Before running: replace CHANGE_ME_STRONG_PASSWORD (do NOT commit the edited file).
-- Note: CREATE DATABASE cannot run inside a transaction block. In DBeaver/pgAdmin use
-- auto-commit mode; in psql run it as is.

CREATE ROLE outageiq_app LOGIN PASSWORD 'CHANGE_ME_STRONG_PASSWORD';

-- RDS admin is not a true superuser; to make it the owner the admin must be a member of the role.
GRANT outageiq_app TO CURRENT_USER;

CREATE DATABASE outageiq OWNER outageiq_app;

-- By default every role can CONNECT to every database. Remove that for this one.
REVOKE ALL ON DATABASE outageiq FROM PUBLIC;
GRANT CONNECT ON DATABASE outageiq TO outageiq_app;

-- Keep the new role out of the other projects' databases is a separate step you control:
-- run `SELECT datname, has_database_privilege('outageiq_app', datname, 'CONNECT')
--       FROM pg_database;` (see verify.sql). If other databases show true, REVOKE CONNECT
-- on them FROM PUBLIC (that affects those projects, so review before doing it).
