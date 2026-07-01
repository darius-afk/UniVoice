CREATE TABLE IF NOT EXISTS polls (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    question TEXT NOT NULL,
    created_by VARCHAR(100), -- User ID din Keycloak
    is_official BOOLEAN DEFAULT FALSE,
    allow_multiple BOOLEAN DEFAULT FALSE,
    target_audience VARCHAR(50) DEFAULT 'all',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- If the table already existed from an older run, ensure new columns exist.
ALTER TABLE polls ADD COLUMN IF NOT EXISTS allow_multiple BOOLEAN DEFAULT FALSE;
ALTER TABLE polls ADD COLUMN IF NOT EXISTS target_audience VARCHAR(50) DEFAULT 'all';

CREATE TABLE IF NOT EXISTS poll_options (
    id SERIAL PRIMARY KEY,
    poll_id INT REFERENCES polls(id) ON DELETE CASCADE,
    text VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS votes (
    id SERIAL PRIMARY KEY,
    poll_id INT REFERENCES polls(id),
    user_id VARCHAR(100), -- User ID din Keycloak
    poll_option_id INT REFERENCES poll_options(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    -- Eliminăm constrângerea unică simplă pentru a permite voturi multiple dacă e cazul
    -- Validarea se va face în cod
);

-- Inserăm un poll de test
INSERT INTO polls (title, question, created_by, is_official, allow_multiple, target_audience)
SELECT 'Test Poll', 'Functioneaza conexiunea la baza de date?', 'admin', TRUE, FALSE, 'all'
WHERE NOT EXISTS (SELECT 1 FROM polls WHERE title = 'Test Poll');

-- Inserăm opțiunile pentru poll-ul de test
INSERT INTO poll_options (poll_id, text)
SELECT p.id, 'DA' FROM polls p
WHERE p.title = 'Test Poll'
    AND NOT EXISTS (SELECT 1 FROM poll_options o WHERE o.poll_id = p.id AND o.text = 'DA');

INSERT INTO poll_options (poll_id, text)
SELECT p.id, 'NU' FROM polls p
WHERE p.title = 'Test Poll'
    AND NOT EXISTS (SELECT 1 FROM poll_options o WHERE o.poll_id = p.id AND o.text = 'NU');