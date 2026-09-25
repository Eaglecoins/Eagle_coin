import os
import re
import uuid
import secrets
import sqlite3
import time
from functools import wraps

from flask import (
    Blueprint,
    request,
    render_template,
    redirect,
    url_for,
    flash,
    session,
    jsonify,
    current_app
)

from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

import database


# =========================================================
# AUTH BLUEPRINT
# =========================================================

auth_bp = Blueprint("auth", __name__)


# =========================================================
# SECURITY CONFIGURATION
# =========================================================

ALLOWED_IMAGE_EXTENSIONS = {
    "jpg",
    "jpeg",
    "png",
    "webp"
}

MAX_UPLOAD_SIZE = 5 * 1024 * 1024  # 5 MB


# =========================================================
# CSRF PROTECTION
# =========================================================

def get_csrf_token():
    """
    Session کے لیے CSRF token بناتا ہے۔
    """
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)

    return session["csrf_token"]


@auth_bp.app_context_processor
def inject_csrf_token():
    """
    Templates میں csrf_token() available کرے گا۔
    """
    return {
        "csrf_token": get_csrf_token
    }


def validate_csrf():
    """
    POST requests کے لیے CSRF token verify کرتا ہے۔
    """
    session_token = session.get("csrf_token")
    form_token = request.form.get("csrf_token")

    # JSON request کے لیے
    if not form_token and request.is_json:
        data = request.get_json(silent=True) or {}
        form_token = data.get("csrf_token")

    if not session_token or not form_token:
        return False

    return secrets.compare_digest(
        str(session_token),
        str(form_token)
    )


# =========================================================
# BASIC INPUT VALIDATION
# =========================================================

def clean_username(username):
    """
    Username کو safely validate کرتا ہے۔
    """
    if not username:
        return None

    username = username.strip()

    # 8-30 characters
    if len(username) < 8 or len(username) > 30:
        return None

    # صرف letters, numbers, underscore, dot
    if not re.fullmatch(r"[A-Za-z0-9_.]+", username):
        return None

    return username


def validate_password(password):
    """
    Strong password validation.
    """
    if not password:
        return False

    if len(password) < 8 or len(password) > 128:
        return False

    return True


def allowed_image(filename):
    """
    صرف allowed image extensions۔
    """
    if not filename or "." not in filename:
        return False

    extension = filename.rsplit(".", 1)[1].lower()
    return extension in ALLOWED_IMAGE_EXTENSIONS


# =========================================================
# SECURE FILE UPLOAD
# =========================================================

def save_uploaded_image(file, prefix="file"):
    """
    Uploaded image کو random filename کے ساتھ save کرتا ہے۔
    """
    if not file or not file.filename:
        return None, None

    if not allowed_image(file.filename):
        return None, "Only JPG, JPEG, PNG and WEBP images are allowed."

    # File size check
    try:
        file.stream.seek(0, os.SEEK_END)
        file_size = file.stream.tell()
        file.stream.seek(0)

        if file_size > MAX_UPLOAD_SIZE:
            return None, "File size must be less than 5 MB."

    except Exception:
        return None, "Unable to verify uploaded file."

    upload_folder = os.path.join(
        current_app.root_path,
        "static",
        "uploads"
    )

    os.makedirs(upload_folder, exist_ok=True)

    original_name = secure_filename(file.filename)
    if not original_name:
        return None, "Invalid file name."

    extension = original_name.rsplit(".", 1)[1].lower()
    random_name = f"{prefix}_{uuid.uuid4().hex}.{extension}"
    file_path = os.path.join(upload_folder, random_name)

    try:
        file.save(file_path)
    except Exception as e:
        current_app.logger.error(f"File upload error: {e}")
        return None, "Unable to save uploaded file."

    return random_name, None


# =========================================================
# LOGIN RATE LIMITING
# =========================================================

_login_attempts = {}


def check_login_rate_limit(username):
    """
    Basic brute-force protection.
    """
    username = (username or "").lower()
    now = time.time()
    record = _login_attempts.get(username)

    if not record:
        return True

    attempts, first_attempt, blocked_until = record

    if blocked_until > now:
        return False

    # 15 minutes کے بعد reset
    if now - first_attempt > 900:
        _login_attempts.pop(username, None)
        return True

    return True


def record_failed_login(username):
    username = (username or "").lower()
    now = time.time()
    record = _login_attempts.get(username)

    if not record:
        _login_attempts[username] = (1, now, 0)
        return

    attempts, first_attempt, blocked_until = record

    if now - first_attempt > 900:
        _login_attempts[username] = (1, now, 0)
        return

    attempts += 1
    if attempts >= 10:
        blocked_until = now + 900

    _login_attempts[username] = (attempts, first_attempt, blocked_until)


def clear_login_attempts(username):
    username = (username or "").lower()
    _login_attempts.pop(username, None)


# =========================================================
# PASSWORD VERIFICATION
# =========================================================

def verify_password_and_upgrade(user, password):
    """
    صرف secure Werkzeug hashes accept کرتا ہے۔
    Legacy SHA256 password ہو تو verify کر کے secure hash میں upgrade کرتا ہے۔
    """
    if not user or not password:
        return False

    stored_password = user["password"]
    if not stored_password:
        return False

    # Modern Werkzeug hash
    if any(stored_password.startswith(p) for p in ("scrypt:", "pbkdf2:", "argon2:")):
        try:
            return check_password_hash(stored_password, password)
        except Exception:
            return False

    # Legacy SHA256 support
    import hashlib
    legacy_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()

    if secrets.compare_digest(stored_password, legacy_hash):
        try:
            new_hash = generate_password_hash(password)
            conn = database.get_db_connection()
            conn.execute(
                "UPDATE users SET password = ? WHERE id = ?",
                (new_hash, user["id"])
            )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            current_app.logger.error(f"Password migration error: {e}")
            return False

    return False


# =========================================================
# USER LOGIN REQUIRED DECORATOR
# =========================================================

def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login first.", "warning")
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped_view


# =========================================================
# VERIFY USER
# =========================================================

def verify_user(username, password):
    username = clean_username(username)
    if not username or not validate_password(password):
        return False, None

    try:
        conn = database.get_db_connection()
        user = conn.execute(
            "SELECT * FROM users WHERE username = ? LIMIT 1",
            (username,)
        ).fetchone()
        conn.close()

        if user and verify_password_and_upgrade(user, password):
            return True, user

        return False, None

    except Exception as e:
        current_app.logger.error(f"verify_user error: {e}")
        return False, None


# =========================================================
# REGISTER
# =========================================================

@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        if not validate_csrf():
            flash("Security validation failed. Please refresh the page and try again.", "danger")
            return redirect(url_for("auth.register"))

        username = clean_username(request.form.get("username"))
        if not username:
            flash("Username must contain 8-30 characters and only letters, numbers, underscore or dot.", "danger")
            return redirect(url_for("auth.register"))

        password = request.form.get("password")
        if not validate_password(password):
            flash("Password must be between 8 and 128 characters.", "danger")
            return redirect(url_for("auth.register"))

        conn = database.get_db_connection()
        existing_user = conn.execute(
            "SELECT id FROM users WHERE username = ? LIMIT 1",
            (username,)
        ).fetchone()
        conn.close()

        if existing_user:
            flash("Username already exists. Please choose another username.", "danger")
            return redirect(url_for("auth.register"))

        name = request.form.get("name", "").strip()
        father_name = request.form.get("father_name", "").strip()
        id_card = request.form.get("id_card", "").strip()
        mobile_no = (
            request.form.get("mobile_no") or request.form.get("mobile") or ""
        ).strip()
        email = request.form.get("email", "").strip().lower()
        address = request.form.get("address", "").strip()
        region = request.form.get("region", "").strip()
        city = request.form.get("city", "").strip()

        if not name or not father_name:
            flash("Name and Father Name are required.", "danger")
            return redirect(url_for("auth.register"))

        if not id_card:
            flash("ID Card / CNIC is required.", "danger")
            return redirect(url_for("auth.register"))

        if not mobile_no:
            flash("Mobile number is required.", "danger")
            return redirect(url_for("auth.register"))

        if not email:
            flash("Email address is required.", "danger")
            return redirect(url_for("auth.register"))

        # Profile picture
        profile_file = request.files.get("profile_pic")
        profile_filename = "default.png"

        if profile_file and profile_file.filename:
            profile_filename, error = save_uploaded_image(profile_file, prefix="profile")
            if error:
                flash(error, "danger")
                return redirect(url_for("auth.register"))

        # Payment proof
        proof_file = request.files.get("deposit_proof")
        if not proof_file or not proof_file.filename:
            flash("Payment proof is required.", "danger")
            return redirect(url_for("auth.register"))

        proof_filename, error = save_uploaded_image(proof_file, prefix="proof")
        if error:
            flash(error, "danger")
            return redirect(url_for("auth.register"))

        # Referral
        raw_referrer = request.form.get("referred_by", "").strip()
        actual_referrer = None

        if raw_referrer:
            conn = database.get_db_connection()
            referrer = conn.execute(
                """
                SELECT username FROM users
                WHERE referral_code = ? OR username = ? OR mobile_no = ?
                LIMIT 1
                """,
                (raw_referrer, raw_referrer, raw_referrer)
            ).fetchone()
            conn.close()

            if referrer:
                actual_referrer = referrer["username"]

        # Payment information
        payment_method = request.form.get("payment_method", "").strip()
        trx_id = request.form.get("trx_id", "").strip()

        allowed_payment_methods = {"JazzCash", "EasyPaisa", "Bank Transfer"}
        if payment_method not in allowed_payment_methods:
            flash("Invalid payment method.", "danger")
            return redirect(url_for("auth.register"))

        if not trx_id:
            flash("Transaction ID is required.", "danger")
            return redirect(url_for("auth.register"))

        user_data = {
            "username": username,
            "password": password,
            "name": name,
            "father_name": father_name,
            "id_card": id_card,
            "mobile_no": mobile_no,
            "email": email,
            "address": address,
            "region": region,
            "city": city,
            "profile_pic": profile_filename,
            "referred_by": actual_referrer,
            "deposit_proof": proof_filename,
            "payment_method": payment_method,
            "trx_id": trx_id,
            "registration_fee": 2000
        }

        success, message = database.register_user_db(user_data)

        if success:
            flash("Your account has been successfully submitted. Admin will approve it after verifying your payment.", "success")
            flash("مزید معلومات کے لیے WhatsApp پر رابطہ کریں: 03075144144", "info")
            return redirect(url_for("auth.login"))

        flash("Registration failed. Please check your information and try again.", "danger")
        current_app.logger.error(f"Registration database error: {message}")
        return redirect(url_for("auth.register"))

    ref_code = request.args.get("ref", "").strip()
    return render_template("register.html", ref_code=ref_code)


# =========================================================
# LOGIN
# =========================================================

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        #if not validate_csrf():
        #    flash("Security validation failed. Please refresh the page and try again.", "danger")
        #   return redirect(url_for("auth.login"))

        username = clean_username(request.form.get("username"))
        password = request.form.get("password", "")

        if not username or not password:
            flash("Username and password are required.", "danger")
            return redirect(url_for("auth.login"))

        if not check_login_rate_limit(username):
            flash("Too many failed login attempts. Please try again after 15 minutes.", "danger")
            return redirect(url_for("auth.login"))

        try:
            conn = database.get_db_connection()
            user = conn.execute(
                "SELECT * FROM users WHERE username = ? LIMIT 1",
                (username,)
            ).fetchone()
            conn.close()
        except Exception as e:
            current_app.logger.error(f"Login database error: {e}")
            flash("A temporary server error occurred. Please try again.", "danger")
            return redirect(url_for("auth.login"))

        if not user or not verify_password_and_upgrade(user, password):
            record_failed_login(username)
            flash("Invalid username or password.", "danger")
            return redirect(url_for("auth.login"))

        clear_login_attempts(username)

        # Session fixation protection
        session.clear()
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["csrf_token"] = secrets.token_urlsafe(32)

        user_status = str(user["status"] or "pending").lower()
        if user_status != "approved":
            session.clear()
            flash("Your account is currently pending approval. Please wait for the admin to verify and approve your account.", "warning")
            return redirect(url_for("auth.login"))

        flash("Login successful!", "success")
        return redirect(url_for("dashboard"))

    return render_template("login.html")


# =========================================================
# CHECK USERNAME
# =========================================================

@auth_bp.route("/check_username", methods=["POST"])
def check_username():
    data = request.get_json(silent=True) or {}
    username = clean_username(data.get("username", ""))

    if not username:
        return jsonify({"status": "empty", "message": "Username must contain at least 3 valid characters."})

    try:
        conn = database.get_db_connection()
        user = conn.execute(
            "SELECT id FROM users WHERE username = ? LIMIT 1",
            (username,)
        ).fetchone()
        conn.close()

        if user:
            return jsonify({"status": "taken", "message": "Username already exists."})
        
        return jsonify({"status": "available", "message": "Username available."})

    except Exception as e:
        current_app.logger.error(f"Username check error: {e}")
        return jsonify({"status": "error", "message": "Unable to check username."}), 500


# =========================================================
# CONVERT REFERRAL BONUS
# =========================================================

@auth_bp.route("/convert-bonus", methods=["POST"])
@login_required
def convert_bonus():
    if not validate_csrf():
        flash("Security validation failed.", "danger")
        return redirect(url_for("dashboard"))

    user_id = session["user_id"]
    conn = database.get_db_connection()

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ? LIMIT 1", (user_id,))
        user = cursor.fetchone()

        if not user:
            conn.rollback()
            flash("User account not found.", "danger")
            return redirect(url_for("dashboard"))

        referral_bonus = float(user["referral_bonus"] or 0)
        if referral_bonus <= 0:
            conn.rollback()
            flash("No referral bonus available to convert.", "warning")
            return redirect(url_for("dashboard"))

        # =========================================================
        # ⚙️ RATE CONTROL CONFIGURATION (کنٹرول سیٹنگز)
        # =========================================================
        USE_FIXED_RATE = True   # True = فکس ریٹ چلے گا | False = لائیو ریٹ چلے گا
        FIXED_RATE_VALUE = 0.01  # یہاں اپنی مرضی کا فکس ریٹ درج کریں
        # =========================================================
  
        if USE_FIXED_RATE:
            current_rate = FIXED_RATE_VALUE
        else:
            # --- Dynamic Live Coin Rate Calculation ---
            admin_data = cursor.execute("SELECT balance, total_balance FROM admin_settings LIMIT 1").fetchone()
            available_coins = admin_data['balance'] if admin_data else 0.0
            total_balance = admin_data['total_balance'] if (admin_data and 'total_balance' in admin_data.keys()) else 0.0

            total_user_coins = cursor.execute('SELECT SUM(coins) FROM users').fetchone()[0] or 0.0
            total_system_coins = total_user_coins + available_coins

            if total_system_coins > 0:
                current_rate = round(total_balance / total_system_coins, 4)
            else:
                current_rate = 0.0

            # اگر فارمولے سے ریٹ 0 آئے تو تاریخ کی اخری ویلیو چیک کریں
            if current_rate <= 0:
                cursor.execute("SELECT rate FROM coin_rate_history ORDER BY id DESC LIMIT 1")
                history_row = cursor.fetchone()
                if history_row:
                    current_rate = float(history_row["rate"] or 0)

        if current_rate <= 0:
            conn.rollback()
            flash("Invalid coin rate.", "danger")
            return redirect(url_for("dashboard"))

        # Rs / Rate = Coins (مثلاً 500 / 50 = 10 Coins)
        earned_coins = referral_bonus / current_rate
        if earned_coins <= 0:
            conn.rollback()
            flash("Invalid coin conversion.", "danger")
            return redirect(url_for("dashboard"))

        current_user_coins = float(user["coins"] or 0)
        new_coins = current_user_coins + earned_coins

        cursor.execute(
            """
            UPDATE users
            SET coins = ?, referral_bonus = 0
            WHERE id = ? AND referral_bonus = ?
            """,
            (new_coins, user_id, referral_bonus)
        )

        if cursor.rowcount != 1:
            conn.rollback()
            flash("Bonus conversion could not be completed. Please try again.", "danger")
            return redirect(url_for("dashboard"))

        # Deduct available system coins
        try:
            cursor.execute(
                """
                UPDATE admin_settings
                SET balance = balance - ?
                WHERE id = (SELECT id FROM admin_settings ORDER BY id DESC LIMIT 1)
                """,
                (earned_coins,)
            )
        except Exception as e:
            current_app.logger.warning(f"Admin balance update skipped: {e}")

        # Coin history
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS coin_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                type TEXT,
                amount REAL,
                description TEXT,
                timestamp DATETIME DEFAULT (DATETIME('now', 'localtime'))
            )
            """
        )

        cursor.execute(
            """
            INSERT INTO coin_history (user_id, type, amount, description)
            VALUES (?, ?, ?, ?)
            """,
            (
                user_id,
                "Referral Bonus",
                earned_coins,
                f"Converted Rs. {referral_bonus:.2f} Bonus to Coins @ Rate {current_rate:.4f}"
            )
        )

        conn.commit()
        flash(f"Success! {earned_coins:.2f} coins added to your account.", "success")

    except Exception as e:
        conn.rollback()
        current_app.logger.error(f"CONVERT BONUS ERROR: {e}")
        flash("Bonus conversion failed. Please try again.", "danger")

    finally:
        conn.close()

    return redirect(url_for("dashboard"))


# =========================================================
# LOGOUT
# =========================================================

@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out successfully.", "success")
    return redirect(url_for("auth.login"))