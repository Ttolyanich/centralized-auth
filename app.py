import os
import re
import sqlite3
import json
import time
from functools import wraps
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from dotenv import load_dotenv

# Загрузка переменных окружения из .env
load_dotenv()
from werkzeug.middleware.proxy_fix import ProxyFix

# Попытка импорта ldap3
try:
    import ldap3
    from ldap3 import Server, Connection, ALL, SUBTREE
    LDAP_AVAILABLE = True
except ImportError:
    LDAP_AVAILABLE = False

# Загрузка конфигурации
CONFIG_PATH = os.getenv("OPENVPN_WEB_CONFIG", "/opt/centralized-auth/config.json")
config = {
    "mode": "auth",
    "secret_key": "default-secret-key-32-chars-long-please-change",
    "node_api_token": "default-token",
    "bind_host": "0.0.0.0",
    "bind_port": 5001,
    # LDAP настройки
    "ldap_enabled": False,
    "ldap_server": "ldap://127.0.0.1:389",
    "ldap_domain": "",
    "ldap_base_dn": "",
    "ldap_bind_user": "",
    "ldap_bind_password": "",
    "ldap_required_group": "",
    "ldap_admin_group": "",
    "ldap_nested_groups": True
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

# Поддержка переменных окружения (.env / Docker)
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

# LDAP переменные
if os.getenv("LDAP_ENABLED"):
    config["ldap_enabled"] = os.getenv("LDAP_ENABLED", "").lower() in ["true", "1", "yes"]
if os.getenv("LDAP_SERVER"):
    config["ldap_server"] = os.getenv("LDAP_SERVER")
if os.getenv("LDAP_DOMAIN"):
    config["ldap_domain"] = os.getenv("LDAP_DOMAIN")
if os.getenv("LDAP_BASE_DN"):
    config["ldap_base_dn"] = os.getenv("LDAP_BASE_DN")
if os.getenv("LDAP_BIND_USER"):
    config["ldap_bind_user"] = os.getenv("LDAP_BIND_USER")
if os.getenv("LDAP_BIND_PASSWORD"):
    config["ldap_bind_password"] = os.getenv("LDAP_BIND_PASSWORD")
if os.getenv("LDAP_REQUIRED_GROUP"):
    config["ldap_required_group"] = os.getenv("LDAP_REQUIRED_GROUP").strip()
if os.getenv("LDAP_ADMIN_GROUP"):
    config["ldap_admin_group"] = os.getenv("LDAP_ADMIN_GROUP").strip()
if os.getenv("LDAP_NESTED_GROUPS"):
    config["ldap_nested_groups"] = os.getenv("LDAP_NESTED_GROUPS", "true").lower() in ["true", "1", "yes"]

# Автогенерация secret_key и node_api_token при первом старте
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

def get_db_connection():
    conn = sqlite3.connect(USERS_DB, timeout=10.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.row_factory = sqlite3.Row
    return conn

# Инициализация базы данных
def init_db():
    from werkzeug.security import generate_password_hash
    db_dir = os.path.dirname(USERS_DB)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
        
    conn = get_db_connection()
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
    # Таблица для ограничения попыток входа (работает корректно при нескольких воркерах Gunicorn)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rate_limits (
            rate_key TEXT NOT NULL,
            attempt_time REAL NOT NULL
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_rate_limits ON rate_limits (rate_key, attempt_time)")
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

init_db()

# SQLite-based rate limiter (безопасен при gunicorn multi-workers)
LOGIN_MAX_ATTEMPTS = 10
LOGIN_WINDOW_SECONDS = 300

def login_rate_limited(key):
    now = time.time()
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Очистка устаревших записей
        cursor.execute("DELETE FROM rate_limits WHERE attempt_time < ?", (now - LOGIN_WINDOW_SECONDS,))
        cursor.execute("SELECT COUNT(*) FROM rate_limits WHERE rate_key = ? AND attempt_time >= ?", (key, now - LOGIN_WINDOW_SECONDS))
        count = cursor.fetchone()[0]
        conn.commit()
        conn.close()
        return count >= LOGIN_MAX_ATTEMPTS
    except Exception as e:
        print(f"Rate limit check error: {e}")
        return False

def register_failed_login(key):
    now = time.time()
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO rate_limits (rate_key, attempt_time) VALUES (?, ?)", (key, now))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Register failed login error: {e}")

# Санитизация имен пользователей
def sanitize_username(username):
    if not username:
        return None
    username = username.strip()
    if not re.match(r"^[a-zA-Z0-9_.@-]{2,64}$", username):
        return None
    return username

# Аутентификация через Active Directory / LDAP с проверкой групп
def authenticate_ldap(username, password):
    """
    Проверяет учетные данные пользователя в домене Active Directory / LDAP.
    Проверяет членство в группе LDAP_REQUIRED_GROUP (если задана).
    Назначает роль 'admin' если состоит в LDAP_ADMIN_GROUP, иначе 'employee'.
    Возвращает: (success: bool, role: str, full_name: str, error_msg: str)
    """
    if not config["ldap_enabled"]:
        return False, None, None, "LDAP отключен"

    if not LDAP_AVAILABLE:
        print("WARNING: LDAP_ENABLED is true, but 'ldap3' module is not installed.")
        return False, None, None, "Модуль ldap3 не установлен на сервере"

    ldap_server = config.get("ldap_server")
    ldap_domain = config.get("ldap_domain")
    base_dn = config.get("ldap_base_dn")
    bind_user = config.get("ldap_bind_user")
    bind_password = config.get("ldap_bind_password")
    req_group = config.get("ldap_required_group")
    admin_group = config.get("ldap_admin_group")

    if not ldap_server or not base_dn:
        return False, None, None, "LDAP сервер или Base DN не настроены"

    # Формируем имя пользователя для поиска (отсекаем доменную приставку если передана)
    clean_user = username
    if "@" in clean_user:
        clean_user = clean_user.split("@")[0]
    elif "\\" in clean_user:
        clean_user = clean_user.split("\\")[-1]

    try:
        print(f"[LDAP] Попытка входа пользователя '{username}' (clean_user: '{clean_user}') на сервер {ldap_server}...")
        server = Server(ldap_server, get_info=ALL, connect_timeout=5)
        
        # Шаг 1: Подключение под сервисной учетной записью для поиска пользователя
        if bind_user and bind_password:
            service_conn = Connection(server, user=bind_user, password=bind_password, auto_bind=True)
        else:
            # Анонимный bind, если сервисный аккаунт не указан
            service_conn = Connection(server, auto_bind=True)

        # Поиск пользователя по sAMAccountName, userPrincipalName или mail
        search_filter = f"(&(objectCategory=person)(objectClass=user)(|(sAMAccountName={clean_user})(sAMAccountName={username})(userPrincipalName={username})(userPrincipalName={clean_user}@{ldap_domain})(mail={username})(mail={clean_user})))"
        attributes = ['distinguishedName', 'sAMAccountName', 'displayName', 'mail', 'memberOf']

        print(f"[LDAP] Поиск в base_dn '{base_dn}' по фильтру: {search_filter}")
        service_conn.search(search_base=base_dn, search_filter=search_filter, search_scope=SUBTREE, attributes=attributes)

        if not service_conn.entries:
            service_conn.unbind()
            print(f"[LDAP] Пользователь '{username}' не найден в каталоге AD.")
            return False, None, None, f"Пользователь '{username}' не найден в домене Active Directory"

        user_entry = service_conn.entries[0]
        user_dn = str(user_entry.distinguishedName)
        display_name = str(user_entry.displayName) if hasattr(user_entry, 'displayName') and user_entry.displayName else clean_user
        print(f"[LDAP] Пользователь найден: DN={user_dn}, displayName={display_name}")
        
        # Получаем список групп пользователя
        user_groups = []
        if hasattr(user_entry, 'memberOf') and user_entry.memberOf:
            user_groups = [str(g).lower() for g in user_entry.memberOf]

        service_conn.unbind()

        # Шаг 2: Проверка пароля пользователя (прямой Simple Bind под DN пользователя)
        user_conn = Connection(server, user=user_dn, password=password)
        if not user_conn.bind():
            print(f"[LDAP] Неверный пароль для DN: {user_dn}")
            return False, None, None, "Неверный пароль доменной учетной записи"
        user_conn.unbind()
        print(f"[LDAP] Пароль пользователя '{username}' успешно подтвержден контроллером домена.")

        # Шаг 3: Проверка членства в разрешенной группе (LDAP_REQUIRED_GROUP)
        def is_member_of_group(target_group):
            if not target_group:
                return False
            target_lower = target_group.lower()
            # Прямое совпадение по DN
            for g in user_groups:
                if target_lower == g or f"cn={target_lower}," in g:
                    return True
            
            # Рекурсивный поиск в AD (LDAP_MATCHING_RULE_IN_CHAIN: 1.2.840.113556.1.4.1941)
            if config.get("ldap_nested_groups") and bind_user and bind_password:
                try:
                    s_conn = Connection(server, user=bind_user, password=bind_password, auto_bind=True)
                    # Если передан короткий CN группы:
                    grp_filter = f"(&(objectCategory=group)(|(cn={target_group})(distinguishedName={target_group})))"
                    s_conn.search(search_base=base_dn, search_filter=grp_filter, search_scope=SUBTREE, attributes=['distinguishedName'])
                    if s_conn.entries:
                        group_dn = str(s_conn.entries[0].distinguishedName)
                        nested_filter = f"(&(objectCategory=person)(objectClass=user)(distinguishedName={user_dn})(memberOf:1.2.840.113556.1.4.1941:={group_dn}))"
                        s_conn.search(search_base=base_dn, search_filter=nested_filter, search_scope=SUBTREE, attributes=['distinguishedName'])
                        is_member = len(s_conn.entries) > 0
                        s_conn.unbind()
                        return is_member
                except Exception as e:
                    print(f"[LDAP] Ошибка проверки вложенных групп: {e}")
            return False

        if req_group:
            if not is_member_of_group(req_group):
                print(f"[LDAP] Отказ в доступе: пользователь '{username}' не состоит в группе '{req_group}'. Группы пользователя: {user_groups}")
                return False, None, None, f"Доступ запрещен: учетная запись не состоит в группе '{req_group}'"

        # Шаг 4: Определение роли (admin или employee)
        role = "employee"
        if admin_group and is_member_of_group(admin_group):
            role = "admin"
        elif not admin_group:
            # Если админ-группа не задана, но пользователь прошел проверку req_group:
            role = "admin"

        print(f"[LDAP] Авторизация успешна! Роль: {role}, имя: {display_name}")
        return True, role, display_name, None

    except Exception as e:
        print(f"[LDAP ERROR] Ошибка соединения с контроллером домена: {e}")
        return False, None, None, f"Ошибка соединения с LDAP контроллером: {e}"

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
    return render_template(
        'auth_admin.html',
        ldap_enabled=config.get("ldap_enabled", False),
        ldap_domain=config.get("ldap_domain", ""),
        ldap_group=config.get("ldap_required_group", "")
    )

# Вход в систему
@app.route('/login', methods=['GET', 'POST'])
def login():
    from werkzeug.security import check_password_hash
    if request.method == 'POST':
        data = request.json or {}
        raw_user = data.get('username', '')
        password = data.get('password', '')
        
        username = sanitize_username(raw_user)
        if not username or not password:
            return jsonify({"error": "Заполните все поля корректными данными"}), 400

        if login_rate_limited(request.remote_addr):
            return jsonify({"error": "Слишком много неудачных попыток входа. Попробуйте через 5 минут."}), 429

        # 1. Сначала проверяем локальную базу пользователей SQLite (fallback для локального admin)
        user = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
            user = cursor.fetchone()
            conn.close()
        except Exception as e:
            print(f"DB error during login: {e}")

        if user and check_password_hash(user['password_hash'], password):
            session["auth_logged_in"] = True
            session["username"] = user['username']
            session["role"] = user['role']
            session["auth_source"] = "local"
            return jsonify({"success": True, "role": user['role']})

        # 2. Если в локальной базе нет или пароль не подошел, пробуем авторизацию через Active Directory / LDAP
        if config["ldap_enabled"]:
            ldap_ok, ldap_role, full_name, ldap_err = authenticate_ldap(username, password)
            if ldap_ok:
                session["auth_logged_in"] = True
                session["username"] = username
                session["role"] = ldap_role
                session["full_name"] = full_name
                session["auth_source"] = "ldap"
                return jsonify({"success": True, "role": ldap_role})
            else:
                register_failed_login(request.remote_addr)
                print(f"[AUTH REJECTED] Пользователь '{username}' не авторизован через LDAP: {ldap_err}")
                return jsonify({"error": ldap_err or "Неверный логин или пароль доменной учетной записи"}), 401

        # Ошибка входа (локальные пользователи)
        register_failed_login(request.remote_addr)
        return jsonify({"error": "Неверный логин или пароль"}), 401
            
    return render_template('login.html')

# Выход из системы
@app.route('/logout', methods=['POST'])
def logout():
    session.pop("auth_logged_in", None)
    session.pop("username", None)
    session.pop("role", None)
    session.pop("auth_source", None)
    return jsonify({"success": True})

# Эндпоинт верификации для нод (OpenVPN, Samba)
@app.route('/api/auth/verify', methods=['POST'])
def api_auth_verify():
    from werkzeug.security import check_password_hash
    token = request.headers.get("X-Node-Token")
    if token != config["node_api_token"]:
        return jsonify({"error": "Unauthorized Node"}), 403
        
    data = request.json or {}
    raw_user = data.get('username', '')
    password = data.get('password', '')
    
    username = sanitize_username(raw_user)
    if not username or not password:
        return jsonify({"error": "Missing or invalid credentials"}), 400

    # Лимит по паре IP-ноды + логин
    rate_key = f"{request.remote_addr}:{username}"
    if login_rate_limited(rate_key):
        return jsonify({"success": False, "error": "Слишком много неудачных попыток входа. Попробуйте позже."}), 429

    # 1. Проверяем локальную БД
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user['password_hash'], password):
            return jsonify({
                "success": True, 
                "username": user['username'],
                "role": user['role'], 
                "source": "local"
            })
    except Exception as e:
        print(f"Error checking local user in verify: {e}")

    # 2. Проверяем Active Directory / LDAP
    if config["ldap_enabled"]:
        ldap_ok, ldap_role, full_name, ldap_err = authenticate_ldap(username, password)
        if ldap_ok:
            return jsonify({
                "success": True, 
                "username": username,
                "role": ldap_role, 
                "full_name": full_name,
                "source": "ldap"
            })
        elif ldap_err and "не состоит в группе" in ldap_err:
            register_failed_login(rate_key)
            return jsonify({"success": False, "error": ldap_err}), 403

    register_failed_login(rate_key)
    return jsonify({"success": False, "error": "Неверный логин или пароль"}), 401

# API Управления пользователями панели
@app.route('/api/users', methods=['GET'])
@login_required
def api_get_users():
    if session.get("role") != "admin":
        return jsonify({"error": "Forbidden: Only admins can view users"}), 403
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, role, created_at FROM users ORDER BY id ASC")
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
    raw_user = data.get('username', '')
    password = data.get('password', '')
    role = data.get('role', 'employee').strip()
    
    username = sanitize_username(raw_user)
    if not username:
        return jsonify({"error": "Недопустимый формат логина"}), 400
    if not password or len(password) < 4:
        return jsonify({"error": "Пароль должен содержать минимум 4 символа"}), 400
    if role not in ['admin', 'employee']:
        role = 'employee'
        
    pw_hash = generate_password_hash(password)
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)", (username, pw_hash, role))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except sqlite3.IntegrityError:
        return jsonify({"error": "Пользователь с таким логином уже существует"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/users/delete/<int:user_id>', methods=['POST'])
@login_required
def api_delete_user(user_id):
    if session.get("role") != "admin":
        return jsonify({"error": "Forbidden: Only admins can delete users"}), 403
    current_user = session.get("username")
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        if not user:
            conn.close()
            return jsonify({"error": "Пользователь не найден"}), 404
        if user['username'] == current_user:
            conn.close()
            return jsonify({"error": "Нельзя удалить текущего авторизованного администратора"}), 400
            
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
    if session.get("auth_source") == "ldap":
        return jsonify({"error": "Пароли доменных учетных записей Active Directory изменяются через Windows / контроллер домена"}), 400

    try:
        conn = get_db_connection()
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
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        if not user:
            conn.close()
            return jsonify({"error": "Пользователь не найден"}), 404
            
        if user['username'] == current_username:
            conn.close()
            return jsonify({"error": "Вы не можете изменить роль самому себе"}), 400
            
        cursor.execute("UPDATE users SET role = ? WHERE id = ?", (new_role, user_id))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# API Сброса пароля пользователя администратором (без пересоздания)
@app.route('/api/users/reset-password/<int:user_id>', methods=['POST'])
@login_required
def api_admin_reset_password(user_id):
    if session.get("role") != "admin":
        return jsonify({"error": "Forbidden: Only admins can reset user passwords"}), 403
        
    data = request.json or {}
    new_password = data.get('new_password', '').strip()
    if not new_password or len(new_password) < 4:
        return jsonify({"error": "Пароль должен содержать минимум 4 символа"}), 400
        
    from werkzeug.security import generate_password_hash
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        if not user:
            conn.close()
            return jsonify({"error": "Пользователь не найден"}), 404
            
        new_hash = generate_password_hash(new_password)
        cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user_id))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": f"Пароль для {user['username']} успешно обновлен"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    init_db()
    app.run(host=config["bind_host"], port=config["bind_port"], debug=False)
