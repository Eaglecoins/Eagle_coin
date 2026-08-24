# پہلے والا ٹیبل ڈراپ کریں یا نئے کالم ایڈ کریں (اگر آپ کا پرانا ڈیٹا اہم نہیں ہے)
conn.execute('''CREATE TABLE IF NOT EXISTS admin_settings 
                (id INTEGER PRIMARY KEY, 
                 balance REAL, 
                 coin_balance REAL DEFAULT 0.0, 
                 web_balance REAL DEFAULT 0.0)''')

# ڈیفالٹ ویلیو ڈالیں (اگر پہلے سے موجود نہیں)
if conn.execute("SELECT COUNT(*) FROM admin_settings").fetchone()[0] == 0:
    conn.execute("INSERT INTO admin_settings (balance, coin_balance, web_balance) VALUES (50000, 0.0, 0.0)")
conn.commit()