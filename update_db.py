import sqlite3

conn = sqlite3.connect('database.db')
cursor = conn.cursor()

# 1. Users ٹیبل کے ضروری کالمز
user_columns = [
    ("referral_bonus", "REAL DEFAULT 0"),
    ("total_withdraw", "REAL DEFAULT 0"),
    ("total_deposit", "REAL DEFAULT 0")
]

for col_name, col_type in user_columns:
    try:
        cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type};")
    except Exception:
        pass

# 2. Deposits ٹیبل کے تمام کالمز (ایک ساتھ)
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
        print(f"Added column: {col_name}")
    except Exception:
        # اگر کالم پہلے سے موجود ہے تو یہ سیفلی سکپ ہو جائے گا
        pass

# 3. Settings ٹیبل
cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value REAL)")
cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('coin_rate', 1.1862)")

conn.commit()
conn.close()

print("ڈیٹا بیس کے تمام کالمز کامیابی سے اپ ڈیٹ ہو گئے!")

import sqlite3

conn = sqlite3.connect('database.db')
cursor = conn.cursor()

# اسکرین شاٹ اور دیگر تمام نام جو بیک اینڈ میں ہو سکتے ہیں
cols = [
    "method", "account_number", "account_name", 
    "trx_id", "screenshot", "proof_image", 
    "payment_proof", "iban", "bank_name", 
    "amount_pkr", "coins", "status"
]

for col in cols:
    try:
        cursor.execute(f"ALTER TABLE deposits ADD COLUMN {col} TEXT;")
        print(f"Added: {col}")
    except:
        pass

conn.commit()
conn.close()
print("ڈیٹا بیس اپ ڈیٹ ہو گیا!")