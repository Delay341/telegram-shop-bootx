import sqlite3, os, threading
DB_PATH = os.getenv("DB_PATH", "data/db.sqlite")
_lock = threading.Lock()
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn
def init_db():
    with _lock:
        conn = get_conn()
        with conn:
            conn.executescript(open("sql/schema.sql","r",encoding="utf-8").read())
        conn.close()
def fetch_one(q,p=()):
    conn=get_conn(); cur=conn.execute(q,p); row=cur.fetchone(); conn.close(); return row
def execute(q,p=()):
    with _lock:
        conn=get_conn()
        with conn: conn.execute(q,p)
        conn.close()
def execute_with_lastrowid(q,p=()):
    with _lock:
        conn=get_conn()
        with conn:
            cur=conn.execute(q,p); lid=cur.lastrowid
        conn.close(); return lid
