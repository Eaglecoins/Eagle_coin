import sqlite3
import hashlib
import uuid
import logging
import os
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, 'database.db')

# ایررز کو فائل میں ریکارڈ کرنے کے لیے
logging.basicConfig(filename='app_errors.log', level=logging.ERROR)

def get_db_connection():
    conn = sqlite3.connect(DB_NAME, timeout=20)
    conn.row_factory = sqlite3.Row
    return conn

def log_activity(username, action):
    try:
        with get_db_connection() as conn:
            conn.execute('INSERT INTO activity_log (username, action) VALUES (?, ?)', (username, action))
            conn.commit()
    except Exception as e:
        logging.error(f"Error logging activity: {e}")

def log_coin_rate(rate):
    try:
        with get_db_connection() as conn:
            conn.execute('INSERT INTO coin_rate_history (rate) VALUES (?)', (rate,))
            conn.commit()
    except Exception as e:
        logging.error(f"Error logging coin rate: {e}")

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Users Table
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        name TEXT,
        father_name TEXT,
        id_card TEXT,
        mobile_no TEXT,
        email TEXT,
        address TEXT,
        region TEXT,
        city TEXT,
        referral_code TEXT,
        referrer_id TEXT,
        referred_by TEXT,
        coins REAL DEFAULT 0.0,
        total_withdraw REAL DEFAULT 0.0,
        payment_screenshot TEXT,
        deposit_proof TEXT,
        payment_method TEXT,
        trx_id TEXT,
        registration_fee REAL DEFAULT 2000,
        profile_pic TEXT, 
        status TEXT DEFAULT 'pending',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')

    # Safe Schema Migrations
    columns_to_add = [
        ("users", "deposit_proof TEXT"),
        ("users", "payment_method TEXT"),
        ("users", "trx_id TEXT"),
        ("users", "registration_fee REAL DEFAULT 2000"),
        ("users", "created_at DATETIME DEFAULT CURRENT_TIMESTAMP"),
        ("withdrawals", "account_number TEXT"),
        ("withdrawals", "trx_id TEXT"),
        ("admin_settings", "total_balance REAL DEFAULT 0")
    ]
    
    for table, col_def in columns_to_add:
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
        except sqlite3.OperationalError:
            pass

    # Tables Setup
    cursor.execute('''CREATE TABLE IF NOT EXISTS deposits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        coins REAL,
        amount REAL,
        status TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS withdrawals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        coins REAL,
        amount REAL,
        method TEXT,
        account_number TEXT,
        iban TEXT,
        status TEXT,
        payment_screenshot TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS password_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        id_card TEXT NOT NULL,
        mobile TEXT NOT NULL,
        profile_pic TEXT,
        cnic_pic TEXT,
        status TEXT DEFAULT 'Pending'
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS activity_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        action TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS admin_settings 
        (id INTEGER PRIMARY KEY, balance REAL, reg_balance REAL DEFAULT 0, ref_balance REAL DEFAULT 0, coin_rate REAL DEFAULT 0)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, key TEXT, value REAL)''')

    if cursor.execute("SELECT COUNT(*) FROM settings WHERE key = 'coin_rate'").fetchone()[0] == 0:
        cursor.execute("INSERT INTO settings (key, value) VALUES ('coin_rate', '0.4706')")

    cursor.execute('''CREATE TABLE IF NOT EXISTS coin_rate_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rate REAL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    if cursor.execute("SELECT COUNT(*) FROM coin_rate_history").fetchone()[0] == 0:
        cursor.execute("INSERT INTO coin_rate_history (rate) VALUES (0.4706)")

    cursor.execute('''CREATE TABLE IF NOT EXISTS announcements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        content TEXT,
        media_type TEXT,
        media_url TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    conn.commit()
    conn.close()

def get_all_referrals(username, conn, depth=0, max_depth=5):
    if depth >= max_depth:
        return []
        
    referrals = []
    cursor = conn.cursor()
    cursor.execute("SELECT username, name FROM users WHERE referred_by = ?", (username,))
    children = cursor.fetchall()
    
    for child in children:
        child_dict = dict(child)
        referrals.append(child_dict)
        referrals.extend(get_all_referrals(child_dict['username'], conn, depth + 1, max_depth))
        
    return referrals

def register_user_db(data):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        hashed_password = generate_password_hash(data['password'])
        referral_code = str(uuid.uuid4())[:8].upper()

        profile_pic = data.get('profile_pic', 'default.png')
        deposit_proof = data.get('deposit_proof') or data.get('payment_screenshot') or 'no_proof.png'

        # Corrected 18 columns and 18 parameters (?)
        cursor.execute('''INSERT INTO users (
                            username, password, name, father_name, id_card,
                            mobile_no, email, address, region, city,
                            referral_code, payment_screenshot, deposit_proof,
                            payment_method, trx_id, registration_fee, profile_pic,
                            referred_by
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                       (
                           data.get('username'),
                           hashed_password,
                           data.get('name'),
                           data.get('father_name'), 
                           data.get('id_card'), 
                           data.get('mobile_no'), 
                           data.get('email'), 
                           data.get('address'), 
                           data.get('region'), 
                           data.get('city'), 
                           referral_code, 
                           deposit_proof,
                           deposit_proof,
                           data.get('payment_method'), 
                           data.get('trx_id'), 
                           data.get('registration_fee', 2000), 
                           profile_pic, 
                           data.get('referred_by')
                       ))
        conn.commit()
        conn.close()
        return True, "User registered successfully"
    except sqlite3.IntegrityError:
        return False, "Username or Email already exists."
    except Exception as e:
        logging.error(f"Error in register_user_db: {e}")
        return False, f"Registration failed due to a server error: {e}"

def verify_user(username, password):
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    if user and check_password_hash(user['password'], password):
        return True, user
    return False, None

def get_current_coin_rate():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = 'coin_rate'")
        result = cursor.fetchone()
        conn.close()
        return float(result[0]) if result else 0.0
    except Exception as e:
        logging.error(f"Error fetching coin rate: {e}")
        return 0.0

def get_user_referral_tree(username, conn, level=1, max_level=5):
    if level > max_level:
        return []

    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            u.id, 
            u.username, 
            u.mobile_no, 
            u.status, 
            u.created_at,
            (SELECT COUNT(*) FROM users WHERE referred_by = u.username) AS direct_team_count
        FROM users u 
        WHERE u.referred_by = ?
    """, (username,))
    
    direct_referrals = cursor.fetchall()
    tree = []
    
    for child in direct_referrals:
        child_dict = dict(child)
        child_dict['level'] = level
        child_dict['sub_referrals'] = get_user_referral_tree(
            child_dict['username'], conn, level + 1, max_level
        )
        tree.append(child_dict)
        
    return tree

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")