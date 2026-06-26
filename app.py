import os
import sqlite3
import json
from functools import wraps
from flask import Flask, render_template, request, jsonify, redirect, url_for, session

# Загрузка конфигурации
CONFIG_PATH = os.getenv("OPENVPN_WEB_CONFIG", "/opt/centralized-auth/config.json")
config = {
    "mode": "auth",
    "secret_key": "default-secret-key-32-chars-long-please-change",
    "node_api_token": "default-token",
    "bind_host": "0.0.0.0"
}

if os.path.exists(CONFIG_PATH):
    try:
        with open(CONFIG_PATH, "r") as f:
            config.update(json.load(f))
    except Exception as e:
        print(f"Error loading config: {e}")

# Автогенерация secret_key при обнаружении дефолтного значения
if config.get("secret_key") == "default-secret-key-32-chars-long-please-change" or not config.get("secret_key"):
    import secrets
    config["secret_key"] = secrets.token_hex(16)
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=2)
        print(f"AUTO-CONFIG: Generated secure random secret_key and saved to {CONFIG_PATH}")
    except Exception as e:
        print(f"Error saving auto-generated secret key: {e}")

# Автогенерация node_api_token
if config.get("node_api_token") == "default-token" or not config.get("node_api_token"):
    import secrets
    config["node_api_token"] = secrets.token_hex(16)
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=2)
        print(f"AUTO-CONFIG: Generated secure random node_api_token and saved to {CONFIG_PATH}")
    except Exception as e:
        print(f"Error saving auto-generated node token: {e}")

app = Flask(__name__)
app.secret_key = config["secret_key"]

# Универсальный middleware для поддержки подпутей (subpath)
class SubpathMiddleware(object):
    def __init__(self, app, prefix=''):
        self.app = app
        self.prefix = prefix

    def __call__(self, environ, start_response):
        script_name = environ.get('HTTP_X_SCRIPT_NAME', self.prefix)
        if script_name:
            environ['SCRIPT_NAME'] = script_name
            path_info = environ.get('PATH_INFO', '')
            if path_info.startswith(script_name):
                environ['PATH_INFO'] = path_info[len(script_name):]
        return self.app(environ, start_response)

app.wsgi_app = SubpathMiddleware(app.wsgi_app, prefix='')

USERS_DB = "/opt/centralized-auth/users.db"

# Инициализация базы данных
def init_db():
    from werkzeug.security import generate_password_hash
    conn = sqlite3.connect(USERS_DB)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'admin',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    
    # Если пользователей нет, создаем администратора по умолчанию
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        import string
        import random
        chars = string.ascii_letters + string.digits
        temp_pass = ''.join(random.choice(chars) for _ in range(12))
        pw_hash = generate_password_hash(temp_pass)
        cursor.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)", ("admin", pw_hash, "admin"))
        conn.commit()
        print("*" * 50)
        print("INITIALIZATION: Created default admin user!")
        print("Username: admin")
        print(f"Password: {temp_pass}")
        print("*" * 50)
    conn.close()

# Декоратор авторизации
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("auth_logged_in"):
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Главный маршрут
@app.route('/')
@login_required
def index():
    return render_template('auth_admin.html')

# Вход в систему
@app.route('/login', methods=['GET', 'POST'])
def login():
    from werkzeug.security import check_password_hash
    if request.method == 'POST':
        data = request.json or {}
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        if not username or not password:
            return jsonify({"error": "Заполните все поля"}), 400
            
        try:
            conn = sqlite3.connect(USERS_DB)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
            user = cursor.fetchone()
            conn.close()
            
            if user and check_password_hash(user['password_hash'], password):
                session["auth_logged_in"] = True
                session["username"] = user['username']
                return jsonify({"success": True})
            else:
                return jsonify({"error": "Неверный логин или пароль"}), 401
        except Exception as e:
            return jsonify({"error": f"Ошибка БД: {e}"}), 500
            
    return render_template('login.html')

# Выход из системы
@app.route('/logout', methods=['POST'])
def logout():
    session.pop("auth_logged_in", None)
    session.pop("username", None)
    return jsonify({"success": True})

# Эндпоинт верификации для нод
@app.route('/api/auth/verify', methods=['POST'])
def api_auth_verify():
    from werkzeug.security import check_password_hash
    token = request.headers.get("X-Node-Token")
    if token != config["node_api_token"]:
        return jsonify({"error": "Unauthorized Node"}), 403
        
    data = request.json or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    if not username or not password:
        return jsonify({"error": "Missing credentials"}), 400
        
    try:
        conn = sqlite3.connect(USERS_DB)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        conn.close()
        
        if user and check_password_hash(user['password_hash'], password):
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "Неверный логин или пароль"}), 401
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# API Управления пользователями
@app.route('/api/users', methods=['GET'])
@login_required
def api_get_users():
    try:
        conn = sqlite3.connect(USERS_DB)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, role, created_at FROM users")
        users = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return jsonify(users)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/users', methods=['POST'])
@login_required
def api_create_user():
    from werkzeug.security import generate_password_hash
    data = request.json or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    role = data.get('role', 'admin').strip()
    
    if not username or not password:
        return jsonify({"error": "Имя пользователя и пароль обязательны"}), 400
        
    pw_hash = generate_password_hash(password)
    try:
        conn = sqlite3.connect(USERS_DB)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)", (username, pw_hash, role))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except sqlite3.IntegrityError:
        return jsonify({"error": "Пользователь с таким именем уже существует"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/users/delete/<int:user_id>', methods=['POST'])
@login_required
def api_delete_user(user_id):
    current_user = session.get("username")
    try:
        conn = sqlite3.connect(USERS_DB)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        if not user:
            conn.close()
            return jsonify({"error": "Пользователь не найден"}), 404
        if user['username'] == current_user:
            conn.close()
            return jsonify({"error": "Нельзя удалить самого себя"}), 400
            
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    init_db()
    bind_host = config.get("bind_host", "0.0.0.0")
    app.run(host=bind_host, port=5001, debug=False)
