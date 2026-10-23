-- Editable UI intent only; canonical Requests and C03 confirmed intent stay in Pipeline.
CREATE TABLE creation_configuration_drafts (
    user_id INTEGER NOT NULL REFERENCES users(id),
    business_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    PRIMARY KEY (user_id, business_id)
);
