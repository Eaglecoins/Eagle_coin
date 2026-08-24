import os
import re
import uuid
import secrets
from functools import wraps
from dotenv import load_dotenv

from flask import (
    Blueprint,
    render_template,
    request,
    session,
    redirect,
    flash,
    url_for,
    current_app
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

import database

# .env فائل کو لوڈ کرنا
load_dotenv()

ADMIN_USER = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASSWORD", "")

admin_bp = Blueprint('admin', __name__)

# اعلانات/میڈیا کے اپ لوڈ فولڈر کی ترتیب
UPLOAD_FOLDER = os.path.join('static', 'uploads', 'announcements')
ALLOWED_MEDIA_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp', 'mp4', 'mkv', 'avi', 'mov'}
MAX_MEDIA_SIZE = 15 * 1024 * 1024  # 15 MB limit


# =========================================================
# SECURITY & DECORATOR HELPERS
# =========================================================

def admin_required(f):
    """ Ensure admin is logged in before accessing route. """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            flash("Please log in as admin first.", "warning")
            return redirect(url_for('admin.admin_login'))
        return f(*args, **kwargs)
    return decorated_function


def validate_admin_csrf():
    """ CSRF Verification for Admin POST requests. """
    session_token = session.get("admin_csrf_token")
    form_token = request.form.get("csrf_token")
    if not session_token or not form_token:
        return False
    return secrets.compare_digest(str(session_token), str(form_token))


def allowed_media_file(filename):
    if not filename or "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in ALLOWED_MEDIA_EXTENSIONS


# =========================================================
# ADMIN LOGIN / LOGOUT
# =========================================================

@admin_bp.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        input_pass = request.form.get('password', '')
        
        # Check against environment admin password safely
        is_correct = False
        if ADMIN_PASS.startswith(('pbkdf2:', 'scrypt:', 'argon2:')):
            is_correct = check_password_hash(ADMIN_PASS, input_pass)
        else:
            is_correct = secrets.compare_digest(
                ADMIN_PASS.encode('utf-8'), 
                input_pass.encode('utf-8')
                )

        if is_correct:
            session.clear()
            session['admin_logged_in'] = True
            session['admin_logged_in'] = True
            session['is_admin'] = True  # <-- یہ نئی لائن یہاں شامل کریں
            session['admin_username'] = ADMIN_USER
            session['admin_username'] = ADMIN_USER
            session['admin_csrf_token'] = secrets.token_urlsafe(32)
            flash("Logged in as Admin successfully.", "success")
            return redirect(url_for('admin.admin_panel'))
        
        flash("غلط پاسورڈ! (Incorrect Admin Password)", "danger")
        return redirect(url_for('admin.admin_login'))

    return render_template('admin_login.html')


@admin_bp.route('/admin_logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    session.pop('admin_username', None)
    session.pop('admin_csrf_token', None)
    flash("Admin logged out successfully.", "info")
    return redirect(url_for('admin.admin_login'))


# =========================================================
# ADMIN DASHBOARD & MAIN PANEL
# =========================================================

@admin_bp.route('/admin_dashboard')
@admin_required
def admin_dashboard():
    conn = database.get_db_connection()
    try:
        admin_data = conn.execute("SELECT balance, ref_balance, total_balance FROM admin_settings LIMIT 1").fetchone()
        admin_balance = float(admin_data['balance']) if admin_data and admin_data['balance'] else 0.0

        total_user_coins = conn.execute('SELECT SUM(coins) FROM users').fetchone()[0] or 0.0
        total_system_coins = total_user_coins + admin_balance

        total_balance = float(admin_data['total_balance']) if (admin_data and 'total_balance' in admin_data.keys() and admin_data['total_balance']) else 0.0

        if total_system_coins > 0:
            calculated_rate = total_balance / total_system_coins
        else:
            calculated_rate = 0.0

        coin_rate = "{:.4f}".format(calculated_rate)

        users = conn.execute('SELECT * FROM users ORDER BY id DESC').fetchall()
        withdrawals = conn.execute("SELECT w.*, u.username FROM withdrawals w JOIN users u ON w.user_id = u.id WHERE LOWER(w.status) = 'pending' ORDER BY w.id DESC").fetchall()
        total_users = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        total_withdraw = conn.execute("SELECT SUM(amount) FROM withdrawals WHERE LOWER(status) = 'approved'").fetchone()[0] or 0.0
        announcements = conn.execute("SELECT * FROM announcements ORDER BY id DESC").fetchall()

        return render_template('admin.html',
                               users=users,
                               withdrawals=withdrawals,
                               total_users=total_users,
                               total_withdraw=total_withdraw,
                               admin_balance=admin_balance,
                               coin_rate=coin_rate,
                               username=session.get('admin_username'),
                               announcements=announcements,
                               csrf_token=session.get('admin_csrf_token'))
    finally:
        conn.close()


@admin_bp.route('/admin')
@admin_required
def admin_panel():
    conn = database.get_db_connection()
    try:
        admin_data = conn.execute("SELECT * FROM admin_settings LIMIT 1").fetchone()
        admin_balance = float(admin_data['balance']) if (admin_data and 'balance' in admin_data.keys() and admin_data['balance']) else 0.0
    except Exception as db_err:
        admin_data = None
        admin_balance = 0.0

        # --- Search, Filter and Pagination Logic ---
        target_username = request.args.get('target_username', '').strip()
        search_date = request.args.get('search_date', '').strip()
        filter_type = request.args.get('filter_type', '').strip()
        
        page = request.args.get('page', 1, type=int)
        per_page = 5
        offset = (page - 1) * per_page

        query = "SELECT *, mobile_no FROM users WHERE 1=1"
        params = []

        if filter_type == 'direct' and target_username:
            query += " AND LOWER(referred_by) = LOWER(?)"
            params.append(target_username)

        elif filter_type == 'indirect' and target_username:
            query += """ AND LOWER(referred_by) IN (
                SELECT LOWER(username) FROM users WHERE LOWER(referred_by) = LOWER(?)
            )"""
            params.append(target_username)

        elif filter_type == 'pending':
            query += " AND LOWER(status) = 'pending'"
            if target_username:
                query += " AND username LIKE ?"
                params.append(f"%{target_username}%")

        elif target_username:
            query += " AND username LIKE ?"
            params.append(f"%{target_username}%")
            
        if search_date:
            query += " AND DATE(created_at) = ?"
            params.append(search_date)

        # Count Filtered Users
        count_query = f"SELECT COUNT(*) FROM ({query})"
        total_users_count = conn.execute(count_query, params).fetchone()[0]
        total_pages = max((total_users_count + per_page - 1) // per_page, 1)

        query += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([per_page, offset])
        
        users = conn.execute(query, params).fetchall()

        total = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        pending = conn.execute("SELECT COUNT(*) FROM users WHERE LOWER(status) = 'pending'").fetchone()[0]
        approved = conn.execute("SELECT COUNT(*) FROM users WHERE LOWER(status) = 'approved'").fetchone()[0]
        
        total_user_coins = conn.execute('SELECT SUM(coins) FROM users').fetchone()[0] or 0.0
        available_coins = admin_balance
        total_system_coins = total_user_coins + available_coins
        
        total_balance = float(admin_data['total_balance']) if (admin_data and 'total_balance' in admin_data.keys() and admin_data['total_balance']) else 0.0
        
        calculated_rate = (total_balance / total_system_coins) if total_system_coins > 0 else 0.0

        withdrawals = conn.execute("SELECT w.*, u.username FROM withdrawals w JOIN users u ON w.user_id = u.id WHERE LOWER(w.status) = 'pending' ORDER BY w.id DESC").fetchall()
        
        # Deposit Data
        pending_deposits = conn.execute("SELECT d.*, u.username FROM deposits d JOIN users u ON d.user_id = u.id WHERE LOWER(d.status) = 'pending' ORDER BY d.id DESC").fetchall()
        approved_deposits = conn.execute("SELECT d.*, u.username FROM deposits d JOIN users u ON d.user_id = u.id WHERE LOWER(d.status) = 'approved' ORDER BY d.id DESC").fetchall()
        
        try:
            logs = conn.execute('SELECT * FROM activity_log ORDER BY id DESC').fetchall()
        except Exception:
            logs = []

        approved_withdrawals = conn.execute("SELECT w.*, u.username FROM withdrawals w JOIN users u ON w.user_id = u.id WHERE LOWER(w.status) = 'approved' ORDER BY w.id DESC").fetchall()
        
        # Password Requests
        try:
            password_requests = conn.execute("SELECT * FROM password_requests WHERE LOWER(status) = 'pending' ORDER BY id DESC").fetchall()
        except Exception:
            password_requests = []

        # Announcements
        try:
            announcements = conn.execute('SELECT * FROM announcements ORDER BY id DESC').fetchall()
        except Exception:
            announcements = []

        # Coin Rate History
        try:
            rate_history = conn.execute("SELECT rate, timestamp FROM coin_rate_history ORDER BY id ASC").fetchall()
            rates = [row['rate'] for row in rate_history]
            timestamps = [row['timestamp'] for row in rate_history]
        except Exception:
            rates = []
            timestamps = []

        return render_template('admin.html', 
                               users=users, total=total, pending=pending, 
                               approved=approved,
                               total_user_coins=total_user_coins, 
                               available_coins=available_coins, 
                               total_system_coins=total_system_coins,
                               admin_balance=available_coins,
                               total_balance=total_balance,
                               coin_rate="{:.4f}".format(calculated_rate), 
                               logs=logs, 
                               withdrawals=withdrawals, 
                               pending_deposits=pending_deposits,
                               approved_deposits=approved_deposits,
                               approved_withdrawals=approved_withdrawals,
                               password_requests=password_requests,
                               announcements=announcements,
                               page=page,
                               rates=rates,
                               timestamps=timestamps,
                               total_pages=total_pages,
                               csrf_token=session.get('admin_csrf_token'))
    finally:
        conn.close()


# =========================================================
# ACTIONS & BALANCE MANAGEMENT
# =========================================================

@admin_bp.route('/update_coins/<int:user_id>/<action>', methods=['POST'])
@admin_required
def update_coins(user_id, action):
    if not validate_admin_csrf():
        flash("Security validation failed.", "danger")
        return redirect(url_for('admin.admin_panel'))

    try:
        amount = float(request.form.get('amount', 0))
        if amount <= 0:
            flash("Please enter a valid positive amount.", "warning")
            return redirect(url_for('admin.admin_panel'))
    except ValueError:
        flash("Invalid amount entered.", "danger")
        return redirect(url_for('admin.admin_panel'))

    conn = database.get_db_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS coin_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                type TEXT,
                amount REAL,
                description TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        if action == 'add':
            conn.execute("UPDATE users SET coins = coins + ? WHERE id = ?", (amount, user_id))
            conn.execute("UPDATE admin_settings SET balance = balance - ?", (amount,))
            conn.execute("""
                INSERT INTO coin_history (user_id, type, amount, description)
                VALUES (?, 'Admin Add', ?, 'Coins added by Admin')
            """, (user_id, amount))
            flash(f"Added {amount} coins to user successfully.", "success")

        elif action == 'subtract':
            conn.execute("UPDATE users SET coins = coins - ? WHERE id = ?", (amount, user_id))
            conn.execute("UPDATE admin_settings SET balance = balance + ?", (amount,))
            conn.execute("""
                INSERT INTO coin_history (user_id, type, amount, description)
                VALUES (?, 'Admin Subtract', ?, 'Coins deducted by Admin')
            """, (user_id, -amount))
            flash(f"Deducted {amount} coins from user successfully.", "success")

        conn.commit()
    except Exception as e:
        conn.rollback()
        current_app.logger.error(f"Error updating coins: {e}")
        flash("Failed to update user coins.", "danger")
    finally:
        conn.close()

    return redirect(url_for('admin.admin_panel'))


@admin_bp.route('/update_admin_balance', methods=['POST'])
@admin_required
def update_admin_balance():
    if not validate_admin_csrf():
        flash("Security validation failed.", "danger")
        return redirect(url_for('admin.admin_panel'))

    try:
        amount = float(request.form.get('amount', 0))
        action = request.form.get('action')
    except ValueError:
        flash("Invalid balance amount.", "danger")
        return redirect(url_for('admin.admin_panel'))

    conn = database.get_db_connection()
    try:
        if action == 'add':
            conn.execute("UPDATE admin_settings SET balance = balance + ?", (amount,))
        elif action == 'subtract':
            conn.execute("UPDATE admin_settings SET balance = balance - ?", (amount,))
        
        conn.commit()
        flash("Admin balance updated.", "success")
    except Exception as e:
        conn.rollback()
        flash("Error updating admin balance.", "danger")
    finally:
        conn.close()

    return redirect(url_for('admin.admin_panel'))


@admin_bp.route('/update_total_balance', methods=['POST'])
@admin_required
def update_total_balance():
    if not validate_admin_csrf():
        flash("Security validation failed.", "danger")
        return redirect(url_for('admin.admin_panel'))

    try:
        amount = float(request.form.get('balance_amount', 0))
        action = request.form.get('action')
    except ValueError:
        flash("Invalid balance amount.", "danger")
        return redirect(url_for('admin.admin_panel'))

    conn = database.get_db_connection()
    try:
        try:
            conn.execute("ALTER TABLE admin_settings ADD COLUMN total_balance REAL DEFAULT 0;")
            conn.commit()
        except Exception:
            pass

        if action == 'add':
            conn.execute("UPDATE admin_settings SET total_balance = total_balance + ?", (amount,))
        elif action == 'subtract':
            conn.execute("UPDATE admin_settings SET total_balance = total_balance - ?", (amount,))

        conn.commit()
        flash("Total balance updated successfully.", "success")
    except Exception as e:
        conn.rollback()
        flash("Error updating total balance.", "danger")
    finally:
        conn.close()

    return redirect(url_for('admin.admin_panel'))


# =========================================================
# APPROVALS & REQUESTS
# =========================================================

@admin_bp.route('/approve_withdraw/<int:id>')
@admin_required
def approve_withdraw(id):
    conn = database.get_db_connection()
    try:
        withd = conn.execute("SELECT * FROM withdrawals WHERE id = ?", (id,)).fetchone()
        if withd and str(withd['status']).lower() == 'pending':
            conn.execute("UPDATE withdrawals SET status = 'Approved' WHERE id = ?", (id,))
            conn.commit()
            flash("Withdrawal approved successfully.", "success")
        else:
            flash("Withdrawal request not found or already processed.", "warning")
    except Exception as e:
        conn.rollback()
        flash("Error approving withdrawal.", "danger")
    finally:
        conn.close()

    return redirect(url_for('admin.admin_panel'))


@admin_bp.route('/approve_deposit/<int:id>')
@admin_required
def approve_deposit(id):
    conn = database.get_db_connection()
    try:
        deposit = conn.execute("SELECT * FROM deposits WHERE id = ?", (id,)).fetchone()

        if deposit and str(deposit['status']).lower() == 'pending':
            user_id = deposit['user_id']
            coins_to_add = float(deposit['coins'] or 0)

            conn.execute("UPDATE users SET coins = coins + ? WHERE id = ?", (coins_to_add, user_id))
            conn.execute("UPDATE admin_settings SET balance = balance - ?", (coins_to_add,))
            conn.execute("UPDATE deposits SET status = 'approved' WHERE id = ?", (id,))
            
            conn.commit()
            flash("Deposit approved and coins added successfully.", "success")
        else:
            flash("Deposit request not found or already processed.", "warning")
    except Exception as e:
        conn.rollback()
        flash("Error approving deposit.", "danger")
    finally:
        conn.close()

    return redirect(url_for('admin.admin_panel'))


@admin_bp.route('/delete_deposit/<int:id>')
@admin_required
def delete_deposit(id):
    conn = database.get_db_connection()
    try:
        conn.execute("DELETE FROM deposits WHERE id = ?", (id,))
        conn.commit()
        flash("Deposit record deleted.", "info")
    finally:
        conn.close()
    
    return redirect(url_for('admin.admin_panel'))


@admin_bp.route('/reset_password_request/<int:req_id>', methods=['POST'])
@admin_required
def reset_password_request(req_id):
    if not validate_admin_csrf():
        flash("Security validation failed.", "danger")
        return redirect(url_for('admin.admin_panel'))

    new_password = request.form.get('new_password', '').strip()
    if not new_password or len(new_password) < 8:
        flash("Password must be at least 8 characters long!", "danger")
        return redirect(url_for('admin.admin_panel'))
        
    hashed_password = generate_password_hash(new_password)
    
    conn = database.get_db_connection()
    try:
        req = conn.execute("SELECT * FROM password_requests WHERE id = ?", (req_id,)).fetchone()
        if req:
            username = req['username']
            conn.execute("UPDATE users SET password = ? WHERE username = ?", (hashed_password, username))
            conn.execute("DELETE FROM password_requests WHERE id = ?", (req_id,))
            conn.commit()
            flash(f"Password for user '{username}' has been reset successfully!", "success")
        else:
            flash("Password reset request not found!", "danger")
    except Exception as e:
        conn.rollback()
        flash("Failed to reset password.", "danger")
    finally:
        conn.close()

    return redirect(url_for('admin.admin_panel'))


@admin_bp.route('/delete_password_request/<int:req_id>', methods=['POST'])
@admin_required
def delete_password_request(req_id):
    if not validate_admin_csrf():
        flash("Security validation failed.", "danger")
        return redirect(url_for('admin.admin_panel'))

    conn = database.get_db_connection()
    try:
        conn.execute("DELETE FROM password_requests WHERE id = ?", (req_id,))
        conn.commit()
        flash("Password request deleted successfully!", "info")
    finally:
        conn.close()

    return redirect(url_for('admin.admin_panel'))


# =========================================================
# ANNOUNCEMENTS & MEDIA UPLODS
# =========================================================

@admin_bp.route('/add_announcement', methods=['POST'])
@admin_required
def add_announcement():
    if not validate_admin_csrf():
        flash("Security validation failed.", "danger")
        return redirect(url_for('admin.admin_panel'))

    title = request.form.get('title', '').strip()
    content = request.form.get('content', '').strip()
    media_type = request.form.get('media_type', '').strip()
    youtube_url = request.form.get('youtube_url', '').strip()
    
    media_url = None

    if media_type == 'youtube' and youtube_url:
        if 'watch?v=' in youtube_url:
            media_url = youtube_url.split('watch?v=')[1].split('&')[0]
        elif 'youtu.be/' in youtube_url:
            media_url = youtube_url.split('youtu.be/')[1].split('?')[0]
        else:
            media_url = youtube_url

    elif media_type in ['image', 'video']:
        file = request.files.get('file')
        if file and file.filename != '':
            if not allowed_media_file(file.filename):
                flash("Invalid file extension for media.", "danger")
                return redirect(url_for('admin.admin_panel'))

            os.makedirs(UPLOAD_FOLDER, exist_ok=True)
            original_name = secure_filename(file.filename)
            ext = original_name.rsplit('.', 1)[1].lower() if '.' in original_name else 'bin'
            saved_filename = f"announcement_{uuid.uuid4().hex}.{ext}"
            file_path = os.path.join(UPLOAD_FOLDER, saved_filename)
            
            try:
                file.save(file_path)
                media_url = f"uploads/announcements/{saved_filename}"
            except Exception as e:
                current_app.logger.error(f"Media save error: {e}")
                flash("Failed to save media file.", "danger")
                return redirect(url_for('admin.admin_panel'))

    conn = database.get_db_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS announcements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                content TEXT,
                media_type TEXT,
                media_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.execute(
            "INSERT INTO announcements (title, content, media_type, media_url) VALUES (?, ?, ?, ?)",
            (title, content, media_type, media_url)
        )
        conn.commit()
        flash("Announcement published successfully!", "success")
    except Exception as e:
        conn.rollback()
        flash("Error publishing announcement.", "danger")
    finally:
        conn.close()

    return redirect(url_for('admin.admin_panel'))


@admin_bp.route("/delete_announcement/<int:post_id>", methods=["POST"])
@admin_required
def delete_announcement(post_id):
    if not validate_admin_csrf():
        flash("Security validation failed.", "danger")
        return redirect(url_for("admin.admin_panel"))

    conn = database.get_db_connection()
    try:
        conn.execute(
            "DELETE FROM announcements WHERE id = ?", (post_id,)
        )
        conn.commit()
        flash("Announcement deleted!", "info")
    finally:
        conn.close()

    return redirect(url_for("admin.admin_panel"))  # <--- یہ لائن اہم ہے

@admin_bp.route('/update_user_status/<int:user_id>/<status>', methods=['POST'])
@admin_required
def update_user_status(user_id, status):
    if not validate_admin_csrf():
        flash("Security validation failed.", "danger")
        return redirect(url_for('admin.admin_panel'))

    if status.lower() not in ['approved', 'rejected', 'pending']:
        flash("Invalid status specified.", "warning")
        return redirect(url_for('admin.admin_panel'))

    conn = database.get_db_connection()
    try:
        conn.execute("UPDATE users SET status = ? WHERE id = ?", (status.lower(), user_id))
        conn.commit()
        flash(f"User status updated to {status.capitalize()}.", "success")
    except Exception as e:
        conn.rollback()
        current_app.logger.error(f"Error updating user status: {e}")
        flash("Failed to update user status.", "danger")
    finally:
        conn.close()

    return redirect(url_for('admin.admin_panel'))


@admin_bp.route('/delete_user/<int:user_id>', methods=['POST'])
@admin_required
def delete_user(user_id):
    if not validate_admin_csrf():
        flash("Security validation failed.", "danger")
        return redirect(url_for('admin.admin_panel'))

    conn = database.get_db_connection()
    try:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        flash("User deleted successfully.", "info")
    except Exception as e:
        conn.rollback()
        current_app.logger.error(f"Error deleting user: {e}")
        flash("Failed to delete user.", "danger")
    finally:
        conn.close()

    return redirect(url_for('admin.admin_panel'))

    return redirect(url_for('admin.admin_panel'))