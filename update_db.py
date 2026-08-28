import sqlite3

conn = sqlite3.connect('database.db')
cursor = conn.cursor()

# 1. Users ٹیبل کے ضروری کالمز (role کا نیا کالم شامل کر دیا گیا ہے)
user_columns = [
    ("referral_bonus", "REAL DEFAULT 0"),
    ("total_withdraw", "REAL DEFAULT 0"),
    ("total_deposit", "REAL DEFAULT 0"),
    ("role", "TEXT DEFAULT 'User'")  # نیا رول کالم (لیڈر/یوزر کے لیے)
]

for col_name, col_type in user_columns:
    try:
        cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type};")
        print(f"Added to users: {col_name}")
    except Exception:
        # اگر کالم پہلے سے موجود ہے تو یہ سیفلی سکپ ہو جائے گا
        pass

# 2. Deposits ٹیبل کے تمام کالمز
deposit_columns = [
    ("method", "TEXT"),
    ("account_number", "TEXT"),
    ("account_name", "TEXT"),
    ("trx_id", "TEXT"),
    ("screenshot", "TEXT"),
    ("proof_image", "TEXT"),
    ("iban", "TEXT"),
    ("bank_name", "TEXT"),
    ("amount_pkr", "REAL"),
    ("coins", "REAL"),
    ("status", "TEXT DEFAULT 'pending'")
]

for col_name, col_type in deposit_columns:
    try:
        cursor.execute(f"ALTER TABLE deposits ADD COLUMN {col_name} {col_type};")
        print(f"Added to deposits: {col_name}")
    except Exception:
        pass

# 3. Settings ٹیبل
cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value REAL)")
cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('coin_rate', 1.1862)")

conn.commit()
conn.close()

print("ڈیٹا بیس کے تمام کالمز (بشمول Role کالم) کامیابی سے اپ ڈیٹ ہو گئے!")