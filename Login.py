from flask import Flask, render_template, request, redirect
import database
import auth

app = Flask(__name__)

# --- آپ کے دیگر تمام روٹس (Home, Dashboard, Add, Delete) یہاں آئیں گے ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # یہاں آپ کے database.py میں verify_user فنکشن کا ہونا ضروری ہے
        user = database.verify_user(username, password)
        
        if user:
            return "Login Successful! Welcome to Dashboard."
        else:
            return "Invalid Username or Password!"
            
    return render_template('login.html')

# --- سرور شروع کرنے کے لیے یہ حصہ سب سے آخر میں ضروری ہے ---
if __name__ == '__main__':
    app.run(debug=True)