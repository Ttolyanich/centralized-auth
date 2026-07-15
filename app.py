import os
import sqlite3
import json
import time
from collections import defaultdict, deque
from functools import wraps
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from dotenv import load_dotenv

# Загрузка переменных окружения из .env
load_dotenv()
from werkzeug.middleware.proxy_fix import ProxyFix

# Загрузка конфигурации
CONFIG_PATH = os.getenv("OPENVPN_WEB_CONFIG", "/opt/centralized-auth/config.json")
config = {
    "mode": "auth",
    "secret_key": "default-secret-key-32-chars-long-please-change",
    "node_api_token": "default-token",
    "bind_host": "0.0.0.0",
    "bind_port": 5001
}

if os.path.exists(CONFIG_PATH):
    try:
        with open(CONFIG_PATH, "r") as f:
            file_config = json.load(f)
            if "bind_port" in file_config:
                file_config["bind_port"] = int(file_config["bind_port"])
            config.update(file_config)
    except Exception as e:
        print(f"Error loading config: {e}")

# Поддержка переменных окружения (Docker)
if os.getenv("SECRET_KEY"):
    config["secret_key"] = os.getenv("SECRET_KEY")
if os.getenv("NODE_API_TOKEN"):
    config["node_api_token"] = os.getenv("NODE_API_TOKEN")
if os.getenv("BIND_HOST"):
    config["bind_host"] = os.getenv("BIND_HOST")
if os.getenv("BIND_PORT"):
    config["bind_port"] = int(os.getenv("BIND_PORT"))
elif os.getenv("PORT"):
    config["bind_port"] = int(os.getenv("PORT"))

# Автогенерация secret_key и node_api_token при обнаружении дефолтных значений
config_changed = False

if config.get("secret_key") == "default-secret-key-32-chars-long-please-change" or not config.get("secret_key"):
    import secrets
    config["secret_key"] = secrets.token_hex(16)
    config_changed = True
    print("AUTO-CONFIG: Generated secure random secret_key")

if config.get("node_api_token") == "default-token" or not config.get("node_api_token"):
    import secrets
    config["node_api_token"] = secrets.token_hex(16)
    config_changed = True
    print("AUTO-CONFIG: Generated secure random node_api_token")

if config_changed:
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=2)
        print(f"AUTO-CONFIG: Config saved to {CONFIG_PATH}")
    except Exception as e:
        print(f"Error saving auto-generated config parameters: {e}")

app = Flask(__name__)
app.secret_key = config["secret_key"]
app.config["PREFERRED_URL_SCHEME"] = os.getenv("PREFERRED_URL_SCHEME", "https")
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)
app.config.update(
    SESSION_COOKIE_NAME=os.getenv("SESSION_COOKIE_NAME", "session"),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=str(os.getenv("SESSION_COOKIE_SECURE", "false")).lower() == "true",
    MAX_CONTENT_LENGTH=int(os.getenv("MAX_CONTENT_LENGTH", 2 * 1024 * 1024)),
)

@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: https:; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'none';"
    )
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response

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

USERS_DB = os.getenv("DATABASE_PATH", "/opt/centralized-auth/users.db")

# Инициализация базы данных
def init_db():
    from werkzeug.security import generate_password_hash
    # Создаем директорию базы данных, если её нет
    db_dir = os.path.dirname(USERS_DB)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
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
        default_pass = os.getenv("ADMIN_PASSWORD", "admin123")
        pw_hash = generate_password_hash(default_pass)
        cursor.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)", ("admin", pw_hash, "admin"))
        conn.commit()
        print("*" * 50)
        print("INITIALIZATION: Created default admin user!")
        print("Username: admin")
        print(f"Password: {default_pass}")
        print("*" * 50)
    conn.close()

# Инициализация базы данных при загрузке модуля
init_db()

# Простой in-memory ограничитель попыток входа (защита от перебора паролей)
_login_attempts = defaultdict(deque)
LOGIN_MAX_ATTEMPTS = 10
LOGIN_WINDOW_SECONDS = 300

def login_rate_limited(key):
    now = time.time()
    attempts = _login_attempts[key]
    while attempts and attempts[0] < now - LOGIN_WINDOW_SECONDS:
        attempts.popleft()
    return len(attempts) >= LOGIN_MAX_ATTEMPTS

def register_failed_login(key):
    _login_attempts[key].append(time.time())

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

        if login_rate_limited(request.remote_addr):
            return jsonify({"error": "Слишком много неудачных попыток входа. Попробуйте позже."}), 429

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
                session["role"] = user['role']
                return jsonify({"success": True})
            else:
                register_failed_login(request.remote_addr)
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

    # Лимит по паре IP-ноды + логин, чтобы перебор одного логина не блокировал всю ноду
    rate_key = f"{request.remote_addr}:{username}"
    if login_rate_limited(rate_key):
        return jsonify({"success": False, "error": "Слишком много неудачных попыток входа. Попробуйте позже."}), 429

    try:
        conn = sqlite3.connect(USERS_DB)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user['password_hash'], password):
            return jsonify({"success": True, "role": user['role']})
        register_failed_login(rate_key)
        return jsonify({"success": False, "error": "Неверный логин или пароль"}), 401
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# API Управления пользователями
@app.route('/api/users', methods=['GET'])
@login_required
def api_get_users():
    if session.get("role") != "admin":
        return jsonify({"error": "Forbidden: Only admins can view users"}), 403
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
    if session.get("role") != "admin":
        return jsonify({"error": "Forbidden: Only admins can create users"}), 403
    from werkzeug.security import generate_password_hash
    data = request.json or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    role = data.get('role', 'employee').strip()
    if role not in ['admin', 'employee']:
        role = 'employee'
    
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
    if session.get("role") != "admin":
        return jsonify({"error": "Forbidden: Only admins can delete users"}), 403
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

# API Смены пароля
@app.route('/api/users/change-password', methods=['POST'])
@login_required
def api_change_password():
    from werkzeug.security import generate_password_hash, check_password_hash
    data = request.json or {}
    old_password = data.get('old_password', '')
    new_password = data.get('new_password', '')
    
    if not old_password or not new_password:
        return jsonify({"error": "Старый и новый пароли обязательны"}), 400
        
    username = session.get("username")
    try:
        conn = sqlite3.connect(USERS_DB)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        
        if not user or not check_password_hash(user['password_hash'], old_password):
            conn.close()
            return jsonify({"error": "Неверный старый пароль"}), 400
            
        new_hash = generate_password_hash(new_password)
        cursor.execute("UPDATE users SET password_hash = ? WHERE username = ?", (new_hash, username))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# API Изменения роли пользователя
@app.route('/api/users/update-role/<int:user_id>', methods=['POST'])
@login_required
def api_update_user_role(user_id):
    if session.get("role") != "admin":
        return jsonify({"error": "Forbidden: Only admins can update roles"}), 403
        
    data = request.json or {}
    new_role = data.get('role', '').strip()
    if new_role not in ['admin', 'employee']:
        return jsonify({"error": "Неверная роль"}), 400
        
    current_username = session.get("username")
    try:
        conn = sqlite3.connect(USERS_DB)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Проверяем существование пользователя
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        if not user:
            conn.close()
            return jsonify({"error": "Пользователь не найден"}), 404
            
        # Запрещаем менять роль самому себе
        if user['username'] == current_username:
            conn.close()
            return jsonify({"error": "Вы не можете изменить роль самому себе"}), 400
            
        cursor.execute("UPDATE users SET role = ? WHERE id = ?", (new_role, user_id))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    init_db()
    app.run(host=config["bind_host"], port=config["bind_port"], debug=False)
