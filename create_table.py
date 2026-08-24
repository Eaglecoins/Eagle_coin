import sqlite3

def create_tables():
    # ڈیٹا بیس سے کنکشن بنانا
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    # 1. یوزرز کا ٹیبل
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            email TEXT,
            password TEXT,
            coins REAL DEFAULT 0.0
        )
    ''')

    # 2. ایڈمن سیٹنگز کا ٹیبل
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            balance REAL DEFAULT 0.0,
            ref_balance REAL DEFAULT 0.0,
            coin_rate REAL DEFAULT 0.0,
            total_balance REAL DEFAULT 0.0
        )
    ''')

    # اگر ایڈمن سیٹنگز بالکل خالی ہو تو اس میں ایک ڈیفالٹ رو (Row) ڈالنا
    cursor.execute("SELECT COUNT(*) FROM admin_settings")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO admin_settings (balance, ref_balance, coin_rate, total_balance) VALUES (0.0, 0.0, 0.0, 0.0)")

    # 3. ڈپازٹ کا ٹیبل
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            coins REAL,
            amount REAL,
            method TEXT,
            account_number TEXT,
            iban TEXT,
            payment_proof TEXT,
            status TEXT
        )
    ''')

    # 4. وڈڈرا کا ٹیبل
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            coins REAL,
            amount REAL,
            method TEXT,
            account_number TEXT,
            status TEXT
        )
    ''')

    conn.commit()
    conn.close()
    print("All tables created successfully with admin default settings!")

    # کنیکشن کو دوبارہ اوپن کر کے نئے کالمز ایڈ کریں
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()

        try:
            cursor.execute("ALTER TABLE coin_rate_history ADD COLUMN change_percent REAL DEFAULT 0.0")
            print("Column change_percent added successfully!")
        except Exception as e:
            print("Column change_percent already exists or skipped.")

        try:
            cursor.execute("ALTER TABLE coin_rate_history ADD COLUMN trend TEXT DEFAULT 'equal'")
            print("Column trend added successfully!")
        except Exception as e:
            print("Column trend already exists or skipped.")

        conn.commit()
        conn.close()
        print("Database columns updated successfully!")
    except Exception as main_e:
        print("Database update error:", main_e)