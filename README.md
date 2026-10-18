# 🔑 Centralized Authentication Server (SSO & LDAP / Active Directory)

[![Stack](https://img.shields.io/badge/python-3.11%2B-blue.svg?style=for-the-badge&logo=python)](https://www.python.org/)
[![Framework](https://img.shields.io/badge/Flask-3.0%2B-lightgrey.svg?style=for-the-badge&logo=flask)](https://flask.palletsprojects.com/)
[![Database](https://img.shields.io/badge/SQLite-3%20WAL-blue.svg?style=for-the-badge&logo=sqlite)](https://www.sqlite.org/)
[![Directory](https://img.shields.io/badge/Active%20Directory-LDAP-0078d4.svg?style=for-the-badge&logo=windows)](https://microsoft.com)

Легковесный, безопасный и централизованный сервер авторизации пользователей (SSO) для распределенных веб-панелей управления (нод), таких как `openvpn-web` и `samba-web`. Позволяет администраторам управлять учетными записями из единой точки, поддерживает гибридную авторизацию (встроенная локальная база + Active Directory / LDAP с фильтрацией по группам) и предоставляет защищенное API для верификации запросов с нод.

---

## ⚡ Основные возможности

* **Гибридная авторизация (Local + Active Directory / LDAP):**
  * Встроенная база SQLite (`users.db`) для локальных администраторов (гарантирует доступ даже при недоступности контроллера домена).
  * Интеграция с корпоративным Active Directory через протокол LDAP (`ldap3`).
  * **Ограничение по группе домена (`LDAP_REQUIRED_GROUP`):** доступ разрешен только пользователям, состоящим в назначенной группе безопасности.
  * **Поддержка вложенных групп AD:** рекурсивный поиск через правило сопоставления `LDAP_MATCHING_RULE_IN_CHAIN` (`1.2.840.113556.1.4.1941`).
  * **Разграничение ролей (`LDAP_ADMIN_GROUP` и `LDAP_ADMIN_USERS`):** члены группы администраторов или пользователи из списка `LDAP_ADMIN_USERS` получают роль `admin`, остальные — `employee`.
  * **Автоматическое кеширование и управление ролями:** вошедшие через LDAP пользователи сохраняются в SQLite (`users.db`), отображаются в списке активных аккаунтов, и администратор может динамически изменять их роль (`admin` / `employee`) через выпадающий список в веб-панели.
* **Безопасное API авторизации нод:** Защищенный эндпоинт `/api/auth/verify` с обязательной проверкой токена `X-Node-Token`.
* **Надежная защита от перебора паролей (Rate Limiting):**
  * Централизованный учет попыток в таблице SQLite в режиме `WAL` (Write-Ahead Logging).
  * Корректно и синхронно работает при любом количестве воркеров Gunicorn.
* **Безопасность по умолчанию:**
  * Хэширование локальных паролей `pbkdf2:sha256` (Werkzeug).
  * Строгая санитизация имен пользователей и защита от инъекций.
  * Безопасные HTTP-заголовки безопасности (CSP, HSTS, X-Frame-Options, nosniff).
* **Стиль оформления:** Премиальный Modern Enterprise SaaS Dark (Slate `#0b1120`, Indigo/Sapphire акценты, поддержка светлой темы).

---

## 📂 Структура проекта

```text
/opt/centralized-auth/
├── app.py                  # Главный исполняемый файл приложения Flask
├── config.json             # Автоматически генерируемый JSON-файл конфигурации
├── users.db                # База данных SQLite с учетными записями и логами rate-limit
├── centralized-auth.service # Файл службы systemd для автозапуска
├── .env.example            # Пример файла конфигурации окружения
├── templates/              # HTML-шаблоны веб-интерфейса
│   ├── login.html          # Шаблон страницы входа
│   └── auth_admin.html     # Панель управления пользователями с KPI карточками
└── static/                 # Статические файлы стилей и скриптов
    ├── css/style.css       # Таблица стилей Modern Enterprise SaaS
    └── js/auth_admin.js    # Скрипты управления учетными записями
```

---

## ⚙️ Конфигурация окружения (`.env`)

Для настройки параметров сервера создайте файл `.env` на основе примера `.env.example`:

| Переменная | Описание | Значение по умолчанию |
| :--- | :--- | :---: |
| `PORT` | Порт для запуска веб-сервера Flask | `5001` |
| `BIND_HOST` | Интерфейс прослушивания | `0.0.0.0` |
| `SECRET_KEY` | Ключ подписи Flask-сессий (`openssl rand -hex 16`) | *Автогенерация* |
| `NODE_API_TOKEN` | Уникальный токен нод для доступа к API | *Автогенерация* |
| `ADMIN_PASSWORD` | Стартовый пароль локального администратора `admin` | `admin123` |
| `LDAP_ENABLED` | Включить авторизацию через Active Directory (`true` / `false`) | `false` |
| `LDAP_SERVER` | Адрес сервера LDAP (`ldap://dc1.company.local:389`) | `ldap://127.0.0.1:389` |
| `LDAP_DOMAIN` | Имя домена (`company.local`) | `—` |
| `LDAP_BASE_DN` | Базовый DN поиска (`DC=company,DC=local`) | `—` |
| `LDAP_BIND_USER` | Сервисная УЗ для поиска пользователей (`svc_auth@company.local`) | `—` |
| `LDAP_BIND_PASSWORD` | Пароль сервисной учетной записи | `—` |
| `LDAP_REQUIRED_GROUP` | Разрешенная группа безопасности домена (CN или имя) | `VPN_Admins` |
| `LDAP_ADMIN_GROUP` | Группа домена, члены которой получают права `admin` панели | `Domain Admins` |
| `LDAP_ADMIN_USERS` | Список логинов администраторов домена через запятую | `—` |
| `LDAP_NESTED_GROUPS` | Рекурсивная проверка во вложенных группах AD | `true` |

---

## 🚀 Варианты развертывания

### Вариант 1. Запуск через Docker (Рекомендуемый)

```bash
git clone https://github.com/Ttolyanich/centralized-auth.git /opt/centralized-auth
cd /opt/centralized-auth
cp .env.example .env
nano .env
docker compose up -d
```

### Вариант 2. Нативный запуск (Systemd)

```bash
pip3 install -r requirements.txt
python3 app.py
sudo cp centralized-auth.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now centralized-auth
```

---

## 🤖 API Интеграция для нод (`/api/auth/verify`)

Используется доверенными узлами (`openvpn-web`, `samba-web`) для верификации пользователя:

* **URL:** `POST /api/auth/verify`
* **Заголовки:**
  * `Content-Type: application/json`
  * `X-Node-Token: <NODE_API_TOKEN>`
* **Тело запроса:**
  ```json
  {
    "username": "user1",
    "password": "user_password"
  }
  ```
* **Ответ (Успешно):**
  ```json
  {
    "success": true,
    "username": "user1",
    "role": "admin",
    "source": "ldap"
  }
  ```
* **Ответ (Отказ в доступе по группе):**
  ```json
  {
    "success": false,
    "error": "Доступ запрещен: пользователь не состоит в группе 'VPN_Admins'"
  }
  ```
