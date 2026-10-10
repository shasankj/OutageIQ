-- 04_grants.sql
-- Run as `outageiq_owner` (the owner of ops and rag), connected to the `outageiq` database.
-- Run AFTER 03_roles.sql. Safe to re-run.

-- Schema access
GRANT USAGE ON SCHEMA ops TO outageiq_reader, outageiq_colleague_ro;
GRANT USAGE ON SCHEMA rag TO outageiq_reader, outageiq_colleague_ro, outageiq_indexer;
-- (the indexer has no access to ops at all)

-- Existing tables
GRANT SELECT ON ALL TABLES IN SCHEMA ops TO outageiq_reader, outageiq_colleague_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA rag TO outageiq_reader, outageiq_colleague_ro;
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA rag TO outageiq_indexer;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA rag TO outageiq_indexer;

-- Future tables created by outageiq_owner (migrations) get the same grants automatically.
ALTER DEFAULT PRIVILEGES IN SCHEMA ops GRANT SELECT ON TABLES TO outageiq_reader, outageiq_colleague_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA rag GRANT SELECT ON TABLES TO outageiq_reader, outageiq_colleague_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA rag GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON TABLES TO outageiq_indexer;
ALTER DEFAULT PRIVILEGES IN SCHEMA rag GRANT USAGE, SELECT ON SEQUENCES TO outageiq_indexer;
