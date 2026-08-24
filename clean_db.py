import sqlite3

def reset_entire_database():
    # اگر آپ کا ڈیٹابیس نام الگ ہے تو یہاں تبدیل کر لیں
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    # تمام ہسٹری اور ڈیٹا کے ٹیبلز کو مکمل خالی کریں
    tables_to_clear = [
        'users',
        'deposits',
        'withdrawals',
        'coin_history',
        'rate_history',
        'announcements',
        'logs'
    ]

    for table in tables_to_clear:
        try:
            cursor.execute(f"DELETE FROM {table};")
            # Auto-increment IDs کو بھی 1 سے شروع کرنے کے لیے ریسیٹ کریں
            cursor.execute(f"DELETE FROM sqlite_sequence WHERE name='{table}';")
            print(f"Cleared table: {table}")
        except sqlite3.OperationalError as e:
            print(f"Skipped table {table} (not found or error): {e}")

    # ایڈمن سیٹنگز کو ڈیفالٹ پر ریسیٹ کریں (اگر ضرورت ہو)
    try:
        cursor.execute("UPDATE admin_settings SET balance = 0 WHERE id = 1;")
    except Exception:
        pass

    conn.commit()
    conn.close()
    print("\n✅ Database has been completely reset! All history and test accounts cleared.")

if __name__ == '__main__':
    reset_entire_database()