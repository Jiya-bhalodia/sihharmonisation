CREATE TABLE IF NOT EXISTS approval_requests (
    id VARCHAR PRIMARY KEY,
    email VARCHAR NOT NULL,
    full_name VARCHAR NOT NULL,
    requested_role VARCHAR NOT NULL,
    status VARCHAR NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at TIMESTAMPTZ,
    decided_by VARCHAR
);
CREATE INDEX IF NOT EXISTS ix_approval_requests_email ON approval_requests (email);
CREATE INDEX IF NOT EXISTS ix_approval_requests_status ON approval_requests (status);
