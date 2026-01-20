PRAGMA foreign_keys = ON;

-- 1) Packs de generación (una petición del usuario)
CREATE TABLE IF NOT EXISTS prompt_pack (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  category      TEXT NOT NULL,
  variant       TEXT NOT NULL,
  requested_n   INTEGER NOT NULL,
  notes         TEXT,
  created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 2) Registro global de combinaciones (para no repetir)
-- scope: por category+variant (si quieres global total, puedes ponerlos a '')
CREATE TABLE IF NOT EXISTS combo_registry (
  combo_key   TEXT PRIMARY KEY,
  category    TEXT NOT NULL,
  variant     TEXT NOT NULL,
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_combo_registry_scope
ON combo_registry(category, variant);

-- 3) Prompts generados
CREATE TABLE IF NOT EXISTS prompt_item (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  pack_id         INTEGER NOT NULL,
  title           TEXT,
  prompt_text     TEXT NOT NULL,
  negative_text   TEXT,
  meta_json       TEXT, -- JSON serializado (seed, width, height, mods, etc.)
  combo_key       TEXT NOT NULL, -- referencia a combo_registry
  status          TEXT NOT NULL DEFAULT 'CREATED', -- CREATED | QUEUED | SENT | DONE | FAILED
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at      TEXT NOT NULL DEFAULT (datetime('now')),

  FOREIGN KEY(pack_id) REFERENCES prompt_pack(id) ON DELETE CASCADE,
  FOREIGN KEY(combo_key) REFERENCES combo_registry(combo_key) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_prompt_item_pack_id ON prompt_item(pack_id);
CREATE INDEX IF NOT EXISTS idx_prompt_item_status ON prompt_item(status);

-- Trigger para updated_at en prompt_item
CREATE TRIGGER IF NOT EXISTS trg_prompt_item_updated_at
AFTER UPDATE ON prompt_item
FOR EACH ROW
BEGIN
  UPDATE prompt_item SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-- 4) Cola de trabajos (para “poner en cola y ya veremos pause/resume”)
CREATE TABLE IF NOT EXISTS queue_job (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  prompt_item_id  INTEGER NOT NULL,
  priority        INTEGER NOT NULL DEFAULT 100,
  status          TEXT NOT NULL DEFAULT 'PENDING', -- PENDING | RUNNING | DONE | FAILED | CANCELLED
  attempts        INTEGER NOT NULL DEFAULT 0,
  last_error      TEXT,
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at      TEXT NOT NULL DEFAULT (datetime('now')),

  FOREIGN KEY(prompt_item_id) REFERENCES prompt_item(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_queue_job_status_priority
ON queue_job(status, priority, created_at);

-- 5) Settings simples en DB (opcional, útil para rutas, flags, etc.)
CREATE TABLE IF NOT EXISTS kv_store (
  k TEXT PRIMARY KEY,
  v TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Trigger para updated_at en queue_job
CREATE TRIGGER IF NOT EXISTS trg_queue_job_updated_at
AFTER UPDATE ON queue_job
FOR EACH ROW
BEGIN
  UPDATE queue_job SET updated_at = datetime('now') WHERE id = NEW.id;
END;
