import sqlite3
import os
from datetime import datetime

DB_FILE = os.environ.get('PLEXTORTION_DB_PATH', 'plextortion.db')

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Ransoms table
    c.execute('''
        CREATE TABLE IF NOT EXISTS ransoms (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL,
            prerequisite TEXT NOT NULL,
            locked_library TEXT NOT NULL,
            progress REAL DEFAULT 0,
            unlocked INTEGER DEFAULT 0,
            threshold REAL DEFAULT 20.0,
            created_at TEXT,
            unlocked_at TEXT,
            custom_from TEXT,
            custom_message TEXT,
            unlock_message TEXT
        )
    ''')
    
    # Payments table (for Venmo bypasses)
    c.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL,
            amount REAL NOT NULL,
            paid_at TEXT
        )
    ''')
    
    # Beer fund tracker
    c.execute('''
        CREATE TABLE IF NOT EXISTS beer_fund (
            id INTEGER PRIMARY KEY,
            total REAL DEFAULT 0,
            last_reset TEXT
        )
    ''')
    
    # Config table
    c.execute('''
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    conn.commit()
    conn.close()
    print("Database initialized!")

def add_ransom(username, prerequisite, locked_library, threshold=20.0, custom_from=None, custom_message=None, unlock_message=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO ransoms (username, prerequisite, locked_library, threshold, created_at, custom_from, custom_message, unlock_message)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (username, prerequisite, locked_library, threshold, datetime.now().isoformat(), custom_from, custom_message, unlock_message))
    conn.commit()
    conn.close()

def get_active_ransoms():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, username, prerequisite, locked_library, progress, unlocked, threshold, created_at, unlocked_at, custom_from, custom_message, unlock_message FROM ransoms WHERE unlocked = 0')
    rows = c.fetchall()
    conn.close()
    
    ransoms = []
    for row in rows:
        ransoms.append({
            'id': row[0],
            'username': row[1],
            'prerequisite': row[2],
            'locked_library': row[3],
            'progress': float(row[4]) if row[4] else 0.0,
            'threshold': float(row[6]) if row[6] else 20.0,
            'created_at': row[7] if len(row) > 7 else None,
            'custom_from': row[9] if len(row) > 9 else None,
            'custom_message': row[10] if len(row) > 10 else None,
            'unlock_message': row[11] if len(row) > 11 else None
        })
    return ransoms

def update_progress(username, progress):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE ransoms SET progress = ? WHERE username = ? AND unlocked = 0',
              (progress, username))
    conn.commit()
    conn.close()

def mark_unlocked(username):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE ransoms SET unlocked = 1, unlocked_at = ? WHERE username = ? AND unlocked = 0',
              (datetime.now().isoformat(), username))
    conn.commit()
    conn.close()

def add_payment(username, amount):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT INTO payments (username, amount, paid_at) VALUES (?, ?, ?)',
              (username, amount, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_beer_fund_total():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT SUM(amount) FROM payments')
    result = c.fetchone()[0]
    conn.close()
    return result or 0

def get_leaderboard():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT username, SUM(amount) as total_paid
        FROM payments
        GROUP BY username
        ORDER BY total_paid DESC
    ''')
    rows = c.fetchall()
    conn.close()
    return rows

def delete_ransom(ransom_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM ransoms WHERE id = ?', (ransom_id,))
    conn.commit()
    conn.close()

def get_completed_ransoms():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT * FROM ransoms WHERE unlocked = 1 ORDER BY unlocked_at DESC')
    rows = c.fetchall()
    conn.close()
    
    ransoms = []
    for row in rows:
        ransoms.append({
            'id': row[0],
            'username': row[1],
            'prerequisite': row[2],
            'locked_library': row[3],
            'progress': row[4],
            'created_at': row[7],
            'unlocked_at': row[8]
        })
    return ransoms

def upgrade_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Add threshold column if it doesn't exist
    try:
        c.execute('ALTER TABLE ransoms ADD COLUMN threshold REAL DEFAULT 20.0')
        print("Added threshold column")
    except:
        pass  # Column already exists
    # Add custom_from column if it doesn't exist
    try:
        c.execute('ALTER TABLE ransoms ADD COLUMN custom_from TEXT')
        print("Added custom_from column")
    except:
        pass  # Column already exists
    # Add custom_message column if it doesn't exist
    try:
        c.execute('ALTER TABLE ransoms ADD COLUMN custom_message TEXT')
        print("Added custom_message column")
    except:
        pass  # Column already exists
    # Add unlock_message column if it doesn't exist
    try:
        c.execute('ALTER TABLE ransoms ADD COLUMN unlock_message TEXT')
        print("Added unlock_message column")
    except:
        pass  # Column already exists
    conn.commit()
    conn.close()

def get_most_used_ransoms(limit=5):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT prerequisite, COUNT(*) as times_used 
        FROM ransoms 
        GROUP BY prerequisite 
        ORDER BY times_used DESC
        LIMIT ?
    ''', (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

def save_config(plex_url, plex_token):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)', ('plex_url', plex_url))
    c.execute('INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)', ('plex_token', plex_token))
    conn.commit()
    conn.close()

def get_config():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)')
    c.execute('SELECT key, value FROM config')
    rows = c.fetchall()
    conn.close()
    return {row[0]: row[1] for row in rows}

# Initialize when imported
if __name__ == '__main__':
    init_db()
