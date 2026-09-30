ALTER TABLE documents ADD COLUMN IF NOT EXISTS correlation_id uuid;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS batch_id uuid;
UPDATE documents SET correlation_id = gen_random_uuid() WHERE correlation_id IS NULL;
ALTER TABLE documents ALTER COLUMN correlation_id SET DEFAULT gen_random_uuid();
ALTER TABLE documents ALTER COLUMN correlation_id SET NOT NULL;
