-- Jira ↔ ADP task mapping table.
-- Tracks which Jira issue key corresponds to which internal task UUID.
-- Applied manually or via a migration; does not replace Alembic migrations.

CREATE TABLE IF NOT EXISTS jira_mapping (
    id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    issue_key     VARCHAR(50)  NOT NULL UNIQUE,
    task_id       UUID         NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    synced_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_jira_mapping_task_id ON jira_mapping (task_id);
