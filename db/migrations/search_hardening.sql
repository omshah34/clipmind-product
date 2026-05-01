-- Gap 293: Postgres — add atomic trigger as safety net for search cache
-- Run this in your Postgres console to ensure search_vector is always fresh.

CREATE OR REPLACE FUNCTION update_clip_search_vector()
RETURNS trigger AS $$
BEGIN
  NEW.search_vector :=
    to_tsvector('english',
      COALESCE(NEW.transcript_text, '') || ' ' ||
      COALESCE(NEW.title, '')
    );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS clip_search_vector_update ON clips;

CREATE TRIGGER clip_search_vector_update
BEFORE INSERT OR UPDATE OF transcript_text, title ON clips
FOR EACH ROW EXECUTE FUNCTION update_clip_search_vector();

-- Gap 295: Enable pg_trgm for fuzzy matching (typo tolerance)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS idx_clips_transcript_trgm
ON clips USING GIN (COALESCE(transcript_text, '') gin_trgm_ops);
