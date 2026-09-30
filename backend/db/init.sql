CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS documents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    filename text NOT NULL,
    content_type text NOT NULL,
    size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
    title text NOT NULL,
    author text NOT NULL,
    category text NOT NULL,
    tags text[] NOT NULL DEFAULT '{}',
    version text NOT NULL,
    status text NOT NULL CHECK (status IN ('PROCESSING', 'INDEXED', 'ERROR')),
    error text,
    content_hash char(64) NOT NULL,
    storage_path text NOT NULL,
    content text,
    search_vector tsvector,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    indexed_at timestamptz,
    correlation_id uuid NOT NULL DEFAULT gen_random_uuid(),
    batch_id uuid
);

CREATE OR REPLACE FUNCTION documents_search_vector_update()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    NEW.search_vector :=
        setweight(to_tsvector('spanish', coalesce(NEW.title, '')), 'A') ||
        setweight(to_tsvector('spanish', coalesce(NEW.author, '') || ' ' || coalesce(NEW.category, '') || ' ' || coalesce(array_to_string(NEW.tags, ' '), '') || ' ' || coalesce(NEW.version, '')), 'B') ||
        setweight(to_tsvector('spanish', coalesce(NEW.content, '')), 'C');
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS documents_search_vector_trigger ON documents;
CREATE TRIGGER documents_search_vector_trigger
BEFORE INSERT OR UPDATE OF title, author, category, tags, version, content
ON documents FOR EACH ROW EXECUTE FUNCTION documents_search_vector_update();

CREATE INDEX IF NOT EXISTS documents_search_gin_idx ON documents USING GIN (search_vector);
CREATE INDEX IF NOT EXISTS documents_status_created_idx ON documents (status, created_at DESC);
CREATE INDEX IF NOT EXISTS documents_content_hash_idx ON documents (content_hash);
