PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, balance REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS pending_topups (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, order_amount REAL, code TEXT, base_amount REAL, created_at INTEGER, status TEXT DEFAULT 'pending', admin_note TEXT);
CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, service_id TEXT, qty INTEGER, link TEXT, price REAL, status TEXT, provider_order_id TEXT, raw_response TEXT, created_at INTEGER, updated_at INTEGER);
