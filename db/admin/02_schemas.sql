-- 02_schemas.sql
-- Run as `outageiq_app` (or admin), connected to the `outageiq` database.
-- Run AFTER 01_extension.sql.

-- Operational tables live in `ops`, vectors in `rag`.
CREATE SCHEMA IF NOT EXISTS ops;
CREATE SCHEMA IF NOT EXISTS rag;

-- Make the app role's default search path predictable.
ALTER ROLE outageiq_app IN DATABASE outageiq SET search_path = ops, rag, public;

-- Hardening of `public` (PG15+ already blocks PUBLIC from creating there).
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
