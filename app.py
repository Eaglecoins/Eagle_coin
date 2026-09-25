import create_table
from flask import Flask, render_template, request, session, redirect, url_for, jsonify, flash
import sqlite3
import uuid
import database
import os
import logging
from functools import wraps
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash

# --- [ 1. بلو پرنٹس امپورٹ ] ---
from auth import auth_bp
from admin import admin_bp

load_dotenv()

app = Flask(__name__)

app.secret_key = os.getenv('SECRET_KEY', 'fallback_secret_key')
# 1. سیشن کو کوکی میں محفوظ رکھنے کے لیے
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# 2. جب آپ ویب سائٹ پر SSL (HTTPS) لگا لیں گے، تو اس لائن کو بھی ان کمنٹ کر دیجیے گا:
# app.config['SESSION_COOKIE_SECURE'] = True
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'database.db')

# --- [ 2. بلو پرنٹس رجسٹریشن ] ---
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)

# Logging Setup
logging.basicConfig(filename='app_errors.log', level=logging.ERROR)

# Helper Decorator for Admin Verification
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # چیک کریں کہ سیشن میں is_admin یا user/admin لاگ ان ہے یا نہیں
        if not session.get('is_admin') and session.get('role') != 'admin' and not session.get('admin'):
            flash("Unauthorized access!", "danger")
            # اگر ایڈمن کا لاگ ان روٹ الگ ہے تو 'admin.admin_login' استعمال کریں
            return redirect(url_for('auth.login')) 
        return f(*args, **kwargs)
    return decorated_function
 
# Database Initialization
with app.app_context():
    database.init_db()
    conn = database.get_db_connection()
    
    conn.execute('''
        CREATE TABLE IF NOT EXISTS coin_rate_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rate REAL NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.execute('''
        CREATE TABLE IF NOT EXISTS contest_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            start_date DATETIME,
            end_date DATETIME,
            status TEXT DEFAULT 'active'
        )
    ''')
    conn.commit()
    conn.close()

# --- Helper Function for Referral Tree ---
def get_user_referral_tree(username_or_id, conn, level=1, max_level=5):
    if level > max_level:
        return []

    cursor = conn.cursor()
    
    # 1. پہلے جس یوزر کی ٹری بنا رہے ہیں اس کی تمام شناختی معلومات (id, username, referral_code) نکالیں
    main_user = cursor.execute("""
        SELECT id, username, referral_code FROM users 
        WHERE id = ? OR username = ? OR referral_code = ?
    """, (str(username_or_id), str(username_or_id), str(username_or_id))).fetchone()

    if not main_user:
        return []

    u_id = str(main_user['id'])
    u_name = str(main_user['username'])
    u_ref = str(main_user['referral_code']) if main_user['referral_code'] else u_name

    # 2. اب ان تینوں میں سے جو بھی referred_by میں ہوگا وہ یوزر مل جائے گا
    cursor.execute("""
        SELECT * FROM users 
        WHERE referred_by = ? OR referred_by = ? OR referred_by = ?
    """, (u_id, u_name, u_ref))
    
    direct_users = cursor.fetchall()
    children = []
    
    for row in direct_users:
        user_dict = dict(row)
        u_identifier = user_dict.get('username') or user_dict.get('id')
        
        # اگلے لیول کے بچوں کو ریکرسیو کال کریں
        sub_children = get_user_referral_tree(u_identifier, conn, level + 1, max_level)
        
        direct_cnt = len(sub_children)
        indirect_cnt = sum(child.get('direct_count', 0) + child.get('indirect_count', 0) for child in sub_children)
        
        raw_status = str(user_dict.get('status', '')).strip().lower()
        status_text = "Approved" if raw_status in ["1", "approved", "true", "active"] else "Pending"

        img = user_dict.get('profile_pic') or user_dict.get('image') or user_dict.get('avatar')
        img_url = f"/static/uploads/{secure_filename(img)}" if (img and secure_filename(img)) else '/static/default_avatar.png'
        
        node = {
            'id': user_dict.get('id'),
            'username': user_dict.get('username'),
            'name': user_dict.get('name') or user_dict.get('full_name') or user_dict.get('username'),
            'email': user_dict.get('email'),
            'mobile_no': user_dict.get('mobile_no'),
            'phone': user_dict.get('mobile_no') or user_dict.get('phone') or 'No Phone',
            'status': user_dict.get('status'),
            'status_text': status_text,
            'coins': user_dict.get('coins', 0.0),
            'profile_pic': img_url,
            'level': level,
            'direct_count': direct_cnt,
            'indirect_count': indirect_cnt,
            'children': sub_children,
            'sub_referrals': sub_children
        }
        children.append(node)
        
    return children


@app.route('/')
def home():
    coin_rate = 0.10
    try:
        conn = database.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT rate FROM coin_rate_history ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        
        if not row:
            cursor.execute("SELECT rate FROM settings ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()

        if row:
            coin_rate = row['rate'] if isinstance(row, dict) or hasattr(row, 'keys') else row[0]
            
        conn.close()
    except Exception as e:
        logging.error(f"Coin rate error: {e}")

    return render_template('index.html', coin_rate=coin_rate)

@app.route('/get_stats')
def get_stats():
    conn = database.get_db_connection() 
    result = conn.execute("SELECT SUM(coins) FROM users").fetchone()
    total_user_coins = result[0] if result and result[0] else 0
    conn.close() 
    
    admin_coins = 50000000 
    grand_total = admin_coins + total_user_coins
    
    return jsonify({
        'user_coins': total_user_coins,
        'grand_total': grand_total
    })
      
# --- Login & Authentication ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password') 
        success, user = database.verify_user(username, password)
        if success:
            if user['status'] != 'approved':
                return "Wait for your account to be approved, or contact us on WhatsApp at 03075144144."
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = user.get('is_admin', False)
            return redirect(url_for('dashboard'))
        return "Wrong Password Please Try Again"
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    conn = database.get_db_connection()
    try:
        user_row = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        if not user_row:
            conn.close()
            return "User not found!"
        user = dict(user_row)

        announcements = conn.execute("SELECT * FROM announcements ORDER BY id DESC").fetchall()

        admin_data = conn.execute("SELECT balance, total_balance FROM admin_settings LIMIT 1").fetchone()
        available_coins = admin_data['balance'] if admin_data else 0.0
        total_balance = admin_data['total_balance'] if admin_data and 'total_balance' in admin_data.keys() else 0.0
        
        total_user_coins = conn.execute('SELECT SUM(coins) FROM users').fetchone()[0] or 0.0
        total_system_coins = total_user_coins + available_coins
        
        if total_system_coins > 0:
            current_rate = round(total_balance / total_system_coins, 4)
        else:
            current_rate = 0.0

        last_saved = conn.execute("SELECT rate FROM coin_rate_history ORDER BY id DESC LIMIT 1").fetchone()
        last_rate_val = float(last_saved['rate']) if (last_saved and last_saved['rate'] is not None) else 0.0

        if current_rate > 0:
            if not last_saved or last_rate_val != current_rate:
                conn.execute("""
                    INSERT INTO coin_rate_history (rate, timestamp)
                    VALUES (?, DATETIME('now', 'localtime'))
                """, (current_rate,))
                conn.commit()

        referral_tree = get_user_referral_tree(user['username'], conn)

        direct_referrals_count = len(referral_tree)
        indirect_referrals_count = sum(child.get('direct_count', 0) + child.get('indirect_count', 0) for child in referral_tree)

        user['phone'] = user.get('mobile_no') or user.get('phone') or user.get('mobile') or user.get('phone_number') or 'No Phone'
        user['profile_pic'] = user.get('profile_pic') or '/static/default_avatar.png'

        total_withdraw_sum = conn.execute("SELECT SUM(amount) FROM withdrawals WHERE user_id = ? AND LOWER(status) = 'approved'", (session['user_id'],)).fetchone()[0] or 0
        total_deposit_sum = conn.execute("SELECT SUM(amount) FROM deposits WHERE user_id = ? AND LOWER(status) = 'approved'", (session['user_id'],)).fetchone()[0] or 0
        
        history = [dict(row) for row in conn.execute("SELECT * FROM withdrawals WHERE user_id = ? ORDER BY id DESC", (session['user_id'],)).fetchall()]
        deposit_history = [dict(row) for row in conn.execute("SELECT * FROM deposits WHERE user_id = ? ORDER BY id DESC", (session['user_id'],)).fetchall()]

        conn.execute("""
            CREATE TABLE IF NOT EXISTS coin_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                type TEXT,
                amount REAL,
                description TEXT,
                timestamp DATETIME DEFAULT (DATETIME('now', 'localtime'))
            )
        """)
        
        coin_history = [dict(row) for row in conn.execute("SELECT * FROM coin_history WHERE user_id = ? ORDER BY id DESC", (session['user_id'],)).fetchall()]

        desc_history = [dict(row) for row in conn.execute("SELECT rate, timestamp FROM coin_rate_history ORDER BY id DESC").fetchall()]
        processed_rate_history = []
        total_records = len(desc_history)

        for i, item in enumerate(desc_history):
            curr_val = item['rate']
            curr_rate = float(curr_val) if (curr_val is not None and float(curr_val) > 0) else current_rate
            
            status = "Live" if i == 0 else "Old Rate"
            direction = "equal"
            pct_change = 0.0
            
            if i + 1 < total_records:
                prev_val = desc_history[i + 1]['rate']
                prev_rate = float(prev_val) if prev_val is not None else 0.0
                
                if prev_rate > 0:
                    diff = curr_rate - prev_rate
                    pct_change = round((diff / prev_rate) * 100, 2)
                    if diff > 0:
                        direction = "up"
                    elif diff < 0:
                        direction = "down"

            processed_rate_history.append({
                'rate': curr_rate,
                'timestamp': item['timestamp'],
                'status': status,
                'direction': direction,
                'pct_change': abs(pct_change)
            })

        def calc_total_team(nodes):
            total = len(nodes)
            for node in nodes:
                total += calc_total_team(node.get('sub_referrals', []))
            return total

        total_referrals_count = calc_total_team(referral_tree)

    finally:
        conn.close()

    return render_template('dashboard.html', 
                            user=user, 
                            children=referral_tree, 
                            referral_tree=referral_tree,
                            total_referrals_count=total_referrals_count,
                            direct_referrals_count=direct_referrals_count,
                            balance=user['coins'] * current_rate, 
                            rate=current_rate,
                            total_withdraw=total_withdraw_sum, 
                            total_deposit_sum=total_deposit_sum,
                            history=history,
                            withdraw_history=history,
                            deposit_history=deposit_history,
                            coin_history=coin_history,
                            coin_transactions=coin_history,
                            rate_history=processed_rate_history,
                            announcements=announcements
    )

@app.route('/update_coins/<int:user_id>/<action>', methods=['POST'])
@admin_required
def update_coins(user_id, action):
    amount = float(request.form.get('amount', 0))
    conn = database.get_db_connection()

    if action == 'add':
        conn.execute("UPDATE users SET coins = coins + ? WHERE id = ?", (amount, user_id))
        conn.execute("""
            INSERT INTO coin_history (user_id, type, amount, description)
            VALUES (?, 'Admin Update', ?, 'Coins added by Admin')
        """, (user_id, amount))
        
    elif action == 'subtract':
        conn.execute("UPDATE users SET coins = coins - ? WHERE id = ?", (amount, user_id))
        conn.execute("""
            INSERT INTO coin_history (user_id, type, amount, description)
            VALUES (?, 'Admin Update', ?, 'Coins deducted by Admin')
        """, (user_id, -amount))

    conn.commit()
    conn.close()
    return redirect('/admin')

@app.route('/approve/<int:user_id>', methods=['POST'])
def approve_user(user_id):
    if not session.get('admin_logged_in') and not session.get('is_admin'):
        flash("Unauthorized access!", "danger")
        return redirect(url_for('admin.admin_login'))

    conn = database.get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    if user:
        # 1. یوزر کا سٹیٹس اپروو کریں
        conn.execute("UPDATE users SET status = 'approved' WHERE id = ?", (user_id,))
        
        # 2. اگر یوزر کا کوئی ریفرر موجود ہے (Level 1)
        if user['referred_by']:
            ref_identifier = user['referred_by']
            
            # Level 1 User کو تلاش کریں (Username, Referral Code یا Phone سے)
            level1_user = conn.execute(
                "SELECT * FROM users WHERE username = ? OR referral_code = ? OR mobile_no = ?",
                (ref_identifier, ref_identifier, ref_identifier)
            ).fetchone()

            if level1_user:
                # Level 1 کا بونس 250 روپے شامل کریں
                conn.execute(
                    "UPDATE users SET referral_bonus = COALESCE(referral_bonus, 0) + 250 WHERE id = ?",
                    (level1_user['id'],)
                )

                # 3. Level 2 User کی تلاش اور بونس (100 روپے)
                if level1_user['referred_by']:
                    l2_identifier = level1_user['referred_by']
                    level2_user = conn.execute(
                        "SELECT * FROM users WHERE username = ? OR referral_code = ? OR mobile_no = ?",
                        (l2_identifier, l2_identifier, l2_identifier)
                    ).fetchone()

                    if level2_user:
                        conn.execute(
                            "UPDATE users SET referral_bonus = COALESCE(referral_bonus, 0) + 100 WHERE id = ?",
                            (level2_user['id'],)
                        )

        conn.commit()
        database.log_activity('admin', f'Approved user ID: {user_id}')
        flash("User approved and referral bonuses distributed successfully!", "success")

    conn.close()
    return redirect(url_for('admin.admin_panel'))

@app.route('/reset_password/<int:user_id>', methods=['POST'])
@admin_required
def reset_password(user_id):
    conn = database.get_db_connection()
    hashed_password = generate_password_hash('123456')
    conn.execute('UPDATE users SET password = ? WHERE id = ?', (hashed_password, user_id))
    conn.commit()
    conn.close()
    return redirect('/admin')

@app.route('/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    # یہاں آپ کے یوزر کو ڈیلیٹ کرنے کا کوڈ ہوگا
    # مثال کے طور پر:
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    return redirect(url_for('admin_dashboard')) # اپنے ڈیش بورڈ والے روٹ کا نام یہاں دیں

@app.route('/upload_profile_pic', methods=['POST'])
def upload_profile_pic():
    if 'user_id' not in session: return redirect('/login')
    if 'file' in request.files:
        file = request.files['file']
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            upload_dir = 'static/uploads'
            if not os.path.exists(upload_dir): os.makedirs(upload_dir)
            file.save(os.path.join(upload_dir, filename))
            
            conn = database.get_db_connection()
            conn.execute("UPDATE users SET profile_pic = ? WHERE id = ?", (filename, session['user_id']))
            conn.commit()
            conn.close()
    return redirect('/dashboard')

@app.route('/deposit', methods=['GET', 'POST'])
def deposit():
    if 'user_id' not in session:
        return redirect('/login')
        
    user_id = session['user_id']
    
    if request.method == 'POST':
        coins = request.form.get('coins')
        amount = request.form.get('amount')
        method = request.form.get('method')
        account_number = request.form.get('account_number')
        iban = request.form.get('iban', '')
        
        payment_proof_file = request.files.get('payment_proof')
        filename = None
        
        if payment_proof_file and payment_proof_file.filename != '':
            filename = secure_filename(payment_proof_file.filename)
            upload_folder = os.path.join('static', 'uploads')
            if not os.path.exists(upload_folder):
                os.makedirs(upload_folder)
            payment_proof_file.save(os.path.join(upload_folder, filename))
        
        conn = database.get_db_connection()
        try:
            conn.execute(
                "INSERT INTO deposits (user_id, coins, amount, method, account_number, iban, payment_proof, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", 
                (user_id, coins, amount, method, account_number, iban, filename, 'pending')
            )
            conn.commit()
            flash("Your Deposit Request Has been Sent Successfully!")
            return redirect('/dashboard')
        except Exception as e:
            logging.error(f"Deposit Error: {e}")
            flash("Something went wrong. Please try again.")
        finally:
            conn.close()
            
        return redirect('/deposit')
        
    conn = database.get_db_connection()
    try:
        admin_data = conn.execute("SELECT balance, total_balance FROM admin_settings LIMIT 1").fetchone()
        available_coins = admin_data['balance'] if admin_data else 0.0
        total_balance = admin_data['total_balance'] if admin_data and 'total_balance' in admin_data.keys() else 0.0
        
        total_user_coins = conn.execute('SELECT SUM(coins) FROM users').fetchone()[0] or 0.0
        total_system_coins = total_user_coins + available_coins
        
        if total_system_coins > 0:
            current_rate = total_balance / total_system_coins
        else:
            current_rate = 0.0
    finally:
        conn.close()
    
    return render_template('deposit.html', rate=current_rate)

@app.route('/withdraw', methods=['GET', 'POST'])
def withdraw():
    if 'user_id' not in session:
        return redirect('/login')
        
    user_id = session['user_id']
    conn = database.get_db_connection()
    
    try:
        try:
            conn.execute("ALTER TABLE withdrawals ADD COLUMN trx_id TEXT")
            conn.commit()
        except Exception:
            pass
            
        admin_data = conn.execute("SELECT balance, total_balance FROM admin_settings LIMIT 1").fetchone()
        available_coins = admin_data['balance'] if admin_data else 0.0
        total_balance = admin_data['total_balance'] if admin_data and 'total_balance' in admin_data.keys() else 0.0
        
        total_user_coins = conn.execute('SELECT SUM(coins) FROM users').fetchone()[0] or 0.0
        total_system_coins = total_user_coins + available_coins
        
        if total_system_coins > 0:
            current_rate = total_balance / total_system_coins
        else:
            current_rate = 0.0
        
        if request.method == 'POST':
            coins = float(request.form['coins'])
            amount_val = request.form.get('final_amount', '0')
            final_amount = float(amount_val) if amount_val else 0.0
            method = request.form['method']
            account_number = request.form['account_number']
            
            trx_id = "TRX" + str(uuid.uuid4().hex[:8].upper())
            
            user = conn.execute("SELECT coins FROM users WHERE id = ?", (user_id,)).fetchone()
            
            if not user or user['coins'] < coins:
                flash("آپ کا بیلنس ناکافی ہے! (Insufficient Balance)")
                return redirect('/withdraw')
                
            conn.execute("UPDATE users SET coins = coins - ? WHERE id = ?", (coins, user_id))
            conn.execute("UPDATE admin_settings SET balance = balance + ?", (coins,))

            conn.execute(
                "INSERT INTO withdrawals (user_id, coins, amount, method, account_number, status, trx_id) VALUES (?, ?, ?, ?, ?, 'pending', ?)",
                (user_id, coins, final_amount, method, account_number, trx_id)
            )

            conn.commit()
            flash("Withdrawal request sent successfully! Track your Order ID on Dashboard.")
            return redirect('/dashboard')

    except Exception as e:
        logging.error(f"Withdraw Error: {str(e)}")
        flash("Something went wrong with withdrawal. Please try again.")
        return redirect('/withdraw')
    finally:
        conn.close()

    return render_template('withdraw.html', rate=current_rate)

@app.route('/withdrawal_history')
def withdrawal_history():
    if 'user_id' not in session: 
        return redirect('/login')

    conn = database.get_db_connection()
    history = [dict(row) for row in conn.execute(
        "SELECT * FROM withdrawals WHERE user_id = ? ORDER BY id DESC", 
        (session['user_id'],)).fetchall()]
    conn.close()

    return render_template('Withdrawal_History.html', history=history)

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        username = request.form.get('username')
        id_card = request.form.get('id_card')
        mobile = request.form.get('mobile')
        
        profile_pic = request.files.get('profile_pic')
        cnic_pic = request.files.get('cnic_pic')
        
        profile_filename = secure_filename(profile_pic.filename) if profile_pic and profile_pic.filename else ''
        cnic_filename = secure_filename(cnic_pic.filename) if cnic_pic and cnic_pic.filename else ''
        
        upload_dir = 'static/uploads'
        if not os.path.exists(upload_dir): os.makedirs(upload_dir)

        if profile_pic and profile_filename:
            profile_pic.save(os.path.join(upload_dir, profile_filename))
        if cnic_pic and cnic_filename:
            cnic_pic.save(os.path.join(upload_dir, cnic_filename))
            
        conn = database.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO password_requests (username, id_card, mobile, profile_pic, cnic_pic)
            VALUES (?, ?, ?, ?, ?)
        ''', (username, id_card, mobile, profile_filename, cnic_filename))
        
        conn.commit()
        conn.close()
        
        flash('Your request to reset your password has been successfully sent to the admin; for further information, please contact 03075144144 via WhatsApp.!', 'success')
        return redirect(url_for('login'))
        
    return render_template('forgot_password.html')

@app.route('/get_pending_counts')
def get_pending_counts():
    conn = database.get_db_connection()
    deposits = conn.execute('SELECT status FROM deposits').fetchall()
    withdrawals = conn.execute('SELECT status FROM withdrawals').fetchall()
    conn.close()
    
    pending_deposits = len([d for d in deposits if d['status'] == 'pending'])
    pending_withdrawals = len([w for w in withdrawals if w['status'] == 'pending'])
    
    return jsonify({'deposits': pending_deposits, 'withdrawals': pending_withdrawals})

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/privacy')
def privacy():
    return render_template('privacy.html')

@app.route('/terms')
def terms():
    return render_template('terms.html') 

@app.route('/contact')
def contact():
    return render_template('contact.html')

from flask import Response

@app.route('/sitemap.xml')
def sitemap():
    xml_content = render_template('sitemap.xml')
    return Response(xml_content, mimetype='text/xml')

@app.route('/robots.txt')
def robots():
    robots_content = """User-agent: *
Disallow: /admin
Disallow: /admin/
Disallow: /database
Sitemap: http://127.0.0.1:5000/sitemap.xml
"""
    return Response(robots_content, mimetype='text/plain')

if __name__ == '__main__':
    if not os.path.exists('static/uploads'): 
        os.makedirs('static/uploads')
    DEBUG_MODE = os.getenv('DEBUG', 'False').lower() == 'true'
    app.run(debug=DEBUG_MODE)