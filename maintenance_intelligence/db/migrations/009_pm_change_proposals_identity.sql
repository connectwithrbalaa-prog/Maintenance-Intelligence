ALTER TABLE pm_change_proposals
  ADD COLUMN IF NOT EXISTS proposer_subject TEXT;

CREATE INDEX IF NOT EXISTS idx_pm_change_proposals_proposer_subject
  ON pm_change_proposals (proposer_subject);