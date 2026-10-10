-- 01_extension.sql
-- Run as your RDS ADMIN (master) user, connected to the `outageiq` database
-- (in your SQL client: same host, user = admin, Database = outageiq).
-- Only rds_superuser can create pgvector on RDS.

CREATE EXTENSION IF NOT EXISTS vector;

SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';
