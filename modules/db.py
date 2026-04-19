import sqlite3, os, json
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'news.db')

def conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    with conn() as c:
        c.executescript('''
            CREATE TABLE IF NOT EXISTS fetch_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL, session_no INTEGER NOT NULL,
                label TEXT NOT NULL, fetched_at TEXT DEFAULT CURRENT_TIMESTAMP,
                articles_added INTEGER DEFAULT 0, UNIQUE(date, session_no)
            );
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL, session_id INTEGER NOT NULL DEFAULT 1,
                session_no INTEGER NOT NULL DEFAULT 1,
                category TEXT NOT NULL, topic TEXT NOT NULL DEFAULT 'general',
                source TEXT, title TEXT NOT NULL, description TEXT,
                url TEXT, title_vi TEXT DEFAULT '', description_vi TEXT DEFAULT '',
                importance INTEGER DEFAULT 3, is_read INTEGER DEFAULT 0,
                fetched_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(date, url)
            );
            CREATE TABLE IF NOT EXISTS article_cache (
                url TEXT PRIMARY KEY,
                content_json TEXT NOT NULL,
                cached_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL UNIQUE, content TEXT NOT NULL DEFAULT '',
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS vocabulary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL, original_text TEXT NOT NULL,
                translated_text TEXT DEFAULT '', type TEXT DEFAULT 'translate',
                article_url TEXT DEFAULT '', article_title TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS fetch_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL, session_no INTEGER DEFAULT 1,
                status TEXT, articles_added INTEGER DEFAULT 0,
                error TEXT, ran_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_art_date ON articles(date);
            CREATE INDEX IF NOT EXISTS idx_art_topic ON articles(topic);
            CREATE INDEX IF NOT EXISTS idx_art_session ON articles(date, session_no);
            CREATE INDEX IF NOT EXISTS idx_ses_date ON fetch_sessions(date);
            CREATE INDEX IF NOT EXISTS idx_vocab_date ON vocabulary(date);
        ''')
        for col, typ in [('session_id','INTEGER DEFAULT 1'),('session_no','INTEGER DEFAULT 1'),
                         ('topic','TEXT DEFAULT "general"'),('importance','INTEGER DEFAULT 3'),
                         ('is_read','INTEGER DEFAULT 0')]:
            try: c.execute(f"ALTER TABLE articles ADD COLUMN {col} {typ}")
            except: pass
        try: c.execute("ALTER TABLE vocabulary ADD COLUMN date TEXT DEFAULT ''")
        except: pass
        try: c.execute("ALTER TABLE vocabulary ADD COLUMN paragraph_index INTEGER DEFAULT -1")
        except: pass
        try: c.execute("CREATE TABLE IF NOT EXISTS article_cache (url TEXT PRIMARY KEY, content_json TEXT NOT NULL, cached_at TEXT DEFAULT CURRENT_TIMESTAMP)")
        except: pass

# ── Sessions ──────────────────────────────────────────────────────────────────
def create_session(date, label):
    with conn() as c:
        row = c.execute("SELECT COALESCE(MAX(session_no),0)+1 AS n FROM fetch_sessions WHERE date=?", (date,)).fetchone()
        sno = row['n']
        c.execute("INSERT OR IGNORE INTO fetch_sessions(date,session_no,label) VALUES(?,?,?)", (date,sno,label))
        sid = c.execute("SELECT id FROM fetch_sessions WHERE date=? AND session_no=?", (date,sno)).fetchone()['id']
    return sid, sno

def get_sessions(date): 
    with conn() as c: return [dict(r) for r in c.execute("SELECT * FROM fetch_sessions WHERE date=? ORDER BY session_no",(date,)).fetchall()]

def update_session_count(sid, count):
    with conn() as c: c.execute("UPDATE fetch_sessions SET articles_added=? WHERE id=?", (count, sid))

def get_existing_urls(date):
    with conn() as c: return {r['url'] for r in c.execute("SELECT url FROM articles WHERE date=? AND url!=''",(date,)).fetchall()}

def get_all_urls():
    with conn() as c: return {r['url'] for r in c.execute("SELECT url FROM articles WHERE url!=''").fetchall()}

# ── Articles ──────────────────────────────────────────────────────────────────
def save_articles(articles, session_id, session_no):
    added = 0
    with conn() as c:
        for a in articles:
            try:
                c.execute('''INSERT OR IGNORE INTO articles
                    (date,session_id,session_no,category,topic,source,title,description,url,title_vi,description_vi,importance)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (a['date'], session_id, session_no, a['category'], a.get('topic','general'),
                     a.get('source',''), a['title'], a.get('description',''), a.get('url',''),
                     a.get('title_vi',''), a.get('description_vi',''), a.get('importance',3)))
                added += c.execute('SELECT changes()').fetchone()[0]
            except: pass
    return added

def get_articles(date):
    with conn() as c: return [dict(r) for r in c.execute('SELECT * FROM articles WHERE date=? ORDER BY session_no,category,topic,id',(date,)).fetchall()]

def get_articles_range(start, end):
    with conn() as c: return [dict(r) for r in c.execute('SELECT * FROM articles WHERE date BETWEEN ? AND ? ORDER BY date,session_no,category,id',(start,end)).fetchall()]

def update_article_importance(aid, imp):
    with conn() as c: c.execute('UPDATE articles SET importance=? WHERE id=?', (imp, aid))

def mark_read(aid):
    with conn() as c: c.execute('UPDATE articles SET is_read=1 WHERE id=?', (aid,))

# ── Article Cache ─────────────────────────────────────────────────────────────
def get_cached_content(url):
    with conn() as c:
        row = c.execute('SELECT content_json FROM article_cache WHERE url=?', (url,)).fetchone()
    return json.loads(row['content_json']) if row else None

def save_cached_content(url, content):
    with conn() as c:
        c.execute('INSERT OR REPLACE INTO article_cache(url,content_json,cached_at) VALUES(?,?,CURRENT_TIMESTAMP)',
                  (url, json.dumps(content, ensure_ascii=False)))

# ── Notes ─────────────────────────────────────────────────────────────────────
def get_note(date):
    with conn() as c:
        row = c.execute('SELECT content FROM notes WHERE date=?',(date,)).fetchone()
    return row['content'] if row else ''

def save_note(date, content):
    with conn() as c:
        c.execute('INSERT INTO notes(date,content,updated_at) VALUES(?,?,CURRENT_TIMESTAMP) ON CONFLICT(date) DO UPDATE SET content=excluded.content,updated_at=excluded.updated_at',(date,content))

# ── Vocabulary ────────────────────────────────────────────────────────────────
def save_vocab(date, original, translated, vtype, url, title, paragraph_index=-1):
    with conn() as c:
        c.execute('INSERT INTO vocabulary(date,original_text,translated_text,type,article_url,article_title,paragraph_index) VALUES(?,?,?,?,?,?,?)',
                  (date, original, translated, vtype, url, title, paragraph_index))
        return c.execute('SELECT last_insert_rowid()').fetchone()[0]

def get_vocab_by_date(date):
    with conn() as c: return [dict(r) for r in c.execute('SELECT * FROM vocabulary WHERE date=? ORDER BY created_at DESC',(date,)).fetchall()]

def get_vocab_all():
    with conn() as c: return [dict(r) for r in c.execute('SELECT * FROM vocabulary ORDER BY created_at DESC').fetchall()]

def delete_vocab(vid):
    with conn() as c: c.execute('DELETE FROM vocabulary WHERE id=?',(vid,))

# ── Misc ──────────────────────────────────────────────────────────────────────
def get_available_dates():
    with conn() as c: return [r['date'] for r in c.execute('SELECT DISTINCT date FROM articles ORDER BY date DESC LIMIT 60').fetchall()]

def get_hot_week(end_date: str, limit: int = 10):
    """Return top N hot articles across the 7-day window ending at end_date.
    Hotness = higher importance, then newer. Only 'international' category by default."""
    try:
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
    except Exception:
        end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=6)
    start_s = start_dt.strftime('%Y-%m-%d')
    end_s = end_dt.strftime('%Y-%m-%d')
    with conn() as c:
        rows = c.execute(
            '''SELECT * FROM articles
               WHERE date BETWEEN ? AND ?
               ORDER BY importance DESC, fetched_at DESC, id DESC
               LIMIT ?''', (start_s, end_s, limit)).fetchall()
    return [dict(r) for r in rows]

def log_fetch(date, sno, status, count=0, error=None):
    with conn() as c: c.execute('INSERT INTO fetch_log(date,session_no,status,articles_added,error) VALUES(?,?,?,?,?)',(date,sno,status,count,error))

def cleanup_old(keep_days=30):
    cutoff = (datetime.now() - timedelta(days=keep_days)).strftime('%Y-%m-%d')
    with conn() as c:
        for t in ('articles','fetch_sessions','notes','fetch_log','vocabulary'):
            c.execute(f'DELETE FROM {t} WHERE date<?',(cutoff,))
        c.execute("DELETE FROM article_cache WHERE cached_at < ?", (cutoff,))

def last_fetch_date():
    with conn() as c:
        row = c.execute("SELECT MAX(date) d FROM fetch_log WHERE status='success'").fetchone()
    return row['d'] if row and row['d'] else None

def has_fetched_today(date):
    with conn() as c:
        row = c.execute("SELECT COUNT(*) n FROM fetch_sessions WHERE date=?",(date,)).fetchone()
    return row['n'] > 0
