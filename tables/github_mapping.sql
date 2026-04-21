CREATE TABLE IF NOT EXISTS github_mapping (
    pr_number INT,
    repo VARCHAR(100),
    task_id UUID REFERENCES tasks(id),
    synced_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(pr_number, repo)
);
