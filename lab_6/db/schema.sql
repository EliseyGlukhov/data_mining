PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS authors (
    author_key     TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    birth_date     TEXT,
    work_count     INTEGER CHECK (work_count IS NULL OR work_count >= 0),
    source         TEXT NOT NULL CHECK (source IN ('openlibrary_api', 'openlibrary_api_author', 'html_books_toscrape')),
    source_url     TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    collected_at   TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS books (
    book_key       TEXT PRIMARY KEY,
    title          TEXT NOT NULL,
    author_key     TEXT REFERENCES authors(author_key) ON UPDATE CASCADE ON DELETE SET NULL,
    price          NUMERIC(10,2) CHECK (price IS NULL OR (price > 0 AND price < 100000)),
    price_currency TEXT CHECK (price_currency IS NULL OR price_currency IN ('USD','EUR','GBP','RUB')),
    rating         SMALLINT CHECK (rating IS NULL OR rating BETWEEN 1 AND 5),
    availability   TEXT,
    category       TEXT,
    isbn           TEXT CHECK (isbn IS NULL OR length(isbn) IN (10,13)),
    publish_year   INTEGER CHECK (publish_year IS NULL OR publish_year BETWEEN 1000 AND 2100),
    source         TEXT NOT NULL CHECK (source IN ('openlibrary_api','html_books_toscrape')),
    source_url     TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    collected_at   TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_books_author    ON books(author_key);
CREATE INDEX IF NOT EXISTS idx_books_category  ON books(category);
CREATE INDEX IF NOT EXISTS idx_books_source    ON books(source);
CREATE INDEX IF NOT EXISTS idx_books_updated   ON books(updated_at);

CREATE TABLE IF NOT EXISTS book_history (
    hist_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    book_key       TEXT NOT NULL,
    title          TEXT NOT NULL,
    author_key     TEXT,
    price          NUMERIC(10,2),
    price_currency TEXT,
    rating         SMALLINT,
    availability   TEXT,
    category       TEXT,
    isbn           TEXT,
    publish_year   INTEGER,
    source         TEXT NOT NULL,
    valid_from     TEXT NOT NULL,
    valid_to       TEXT,
    is_current     INTEGER NOT NULL DEFAULT 1 CHECK (is_current IN (0,1))
);

CREATE INDEX IF NOT EXISTS idx_hist_book    ON book_history(book_key, valid_from);
CREATE INDEX IF NOT EXISTS idx_hist_current ON book_history(is_current);

CREATE TABLE IF NOT EXISTS rejects (
    reject_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    book_key    TEXT,
    payload     TEXT NOT NULL,
    reason      TEXT NOT NULL,
    field       TEXT,
    step        TEXT NOT NULL,
    rejected_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rejects_step   ON rejects(step);
CREATE INDEX IF NOT EXISTS idx_rejects_reason ON rejects(reason);

CREATE TABLE IF NOT EXISTS load_runs (
    run_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at     TEXT NOT NULL,
    finished_at    TEXT,
    rows_inserted  INTEGER DEFAULT 0,
    rows_updated   INTEGER DEFAULT 0,
    rows_unchanged INTEGER DEFAULT 0,
    rows_rejected  INTEGER DEFAULT 0,
    verdict        TEXT
);

CREATE TABLE IF NOT EXISTS quality_metrics (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER REFERENCES load_runs(run_id),
    metric_name     TEXT NOT NULL,
    value           REAL NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('green','yellow','red')),
    threshold_green REAL,
    threshold_yellow REAL,
    measured_at     TEXT NOT NULL
);