-- ==============================================================================
-- Sahayak Database Role Separation Bootstrap Script
-- ==============================================================================
-- Enforces AGENTS.md §7.3 and tasks.md T4.1:
-- 1. sahayak_migrator: Used during CI/CD expand-only migrations (has DDL permissions).
-- 2. sahayak_app: Used at runtime by FastAPI & Arq worker (DML only: SELECT, INSERT, UPDATE, DELETE).
-- The app role CANNOT execute DDL (CREATE, DROP, ALTER) in any schema.
-- ==============================================================================

-- 1. Create Roles
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'sahayak_migrator') THEN
    CREATE ROLE sahayak_migrator LOGIN PASSWORD '${MIGRATOR_PASSWORD}';
  END IF;

  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'sahayak_app') THEN
    CREATE ROLE sahayak_app LOGIN PASSWORD '${APP_PASSWORD}';
  END IF;
END
$$;

-- 2. Grant Database Connect
GRANT CONNECT ON DATABASE sahayak TO sahayak_migrator;
GRANT CONNECT ON DATABASE sahayak TO sahayak_app;

-- 3. Revoke public schema defaults
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON DATABASE sahayak FROM PUBLIC;

-- 4. Schemas Setup (core, academics, productivity, finance, etc.)
CREATE SCHEMA IF NOT EXISTS core AUTHORIZATION sahayak_migrator;
CREATE SCHEMA IF NOT EXISTS academics AUTHORIZATION sahayak_migrator;

-- Grant schema usage
GRANT USAGE, CREATE ON SCHEMA core TO sahayak_migrator;
GRANT USAGE, CREATE ON SCHEMA academics TO sahayak_migrator;

-- App role gets USAGE only (can access tables, cannot CREATE new tables/types/views)
GRANT USAGE ON SCHEMA core TO sahayak_app;
GRANT USAGE ON SCHEMA academics TO sahayak_app;

-- 5. Grant DML Permissions to App Role
-- Existing tables in core and academics
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA core TO sahayak_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA academics TO sahayak_app;

-- Sequences (for autoincrement / ID generators)
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA core TO sahayak_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA academics TO sahayak_app;

-- 6. Default Privileges for Future Tables created by Migrator
ALTER DEFAULT PRIVILEGES FOR ROLE sahayak_migrator IN SCHEMA core
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO sahayak_app;

ALTER DEFAULT PRIVILEGES FOR ROLE sahayak_migrator IN SCHEMA academics
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO sahayak_app;

ALTER DEFAULT PRIVILEGES FOR ROLE sahayak_migrator IN SCHEMA core
    GRANT USAGE, SELECT ON SEQUENCES TO sahayak_app;

ALTER DEFAULT PRIVILEGES FOR ROLE sahayak_migrator IN SCHEMA academics
    GRANT USAGE, SELECT ON SEQUENCES TO sahayak_app;
