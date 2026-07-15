# 🔑 Centralized Authentication Server

[![Stack](https://img.shields.io/badge/python-3.10%2B-blue.svg?style=for-the-badge&logo=python)](https://www.python.org/)
[![Framework](https://img.shields.io/badge/Flask-3.0%2B-lightgrey.svg?style=for-the-badge&logo=flask)](https://flask.palletsprojects.com/)
[![Database](https://img.shields.io/badge/SQLite-3-blue.svg?style=for-the-badge&logo=sqlite)](https://www.sqlite.org/)

Легковесный, безопасный и централизованный сервер авторизации пользователей (SSO) для распределенных веб-панелей управления (нод), таких как `openvpn-web` и `samba-web`. Позволяет администраторам управлять учетными записями из единой точки, предоставляя защищенное API для верификации запросов с нод.

<img width="1385" height="666" alt="image" src="https://github.com/user-attachments/assets/22998dd4-d903-4c0f-a8ac-4f543321362b" />

---

## ⚡ Основные возможности

* **Централизованная БД пользователей:** Хранение учетных записей во встроенной базе данных SQLite (`users.db`).
* **Безопасное API авторизации нод:** Защищенный эндпоинт `/api/auth/verify` с обязательной проверкой токена `X-Node-Token`.
* **Адаптивный веб-интерфейс:** Панель управления пользователями (создание, удаление, смена ролей: `admin`, `employee`).
* **Безопасность по умолчанию:**
  * Хэширование паролей с использованием `pbkdf2:sha256` (Werkzeug).
  * Автоматическая генерация секретных токенов и ключей сессий при первом старте.
  * Ограничитель попыток входа на `/login` и `/api/auth/verify` — защита от перебора паролей.
  * Безопасные HTTP-заголовки безопасности и защита от XSS/CSRF.
* **Фирменный стиль:** Современная красно-черная тема оформления.

---

## 📂 Структура проекта

```text
/opt/centralized-auth/
├── app.py                  # Главный исполняемый файл приложения Flask
├── config.json             # Автоматически генерируемый JSON-файл конфигурации
├── users.db                # База данных SQLite с учетными записями
├── centralized-auth.service # Файл службы systemd для автозапуска
├── .env.example            # Пример файла конфигурации окружения
├── templates/              # HTML-шаблоны веб-интерфейса
│   ├── login.html          # Шаблон страницы входа
│   └── auth_admin.html     # Панель управления пользователями
└── static/                 # Статические файлы стилей и скриптов
    ├── css/style.css       # Фирменная таблица стилей
    └── js/auth_admin.js    # JS-скрипты управления пользователями
```

---

## ⚙️ Конфигурация окружения (`.env`)

Для настройки параметров сервера создайте файл `.env` на основе примера `.env.example`:

| Переменная | Описание | Значение по умолчанию |
| :--- | :--- | :---: |
| `PORT` | Порт для запуска веб-сервера Flask | `5001` |
| `BIND_HOST` | Интерфейс прослушивания | `0.0.0.0` |
| `SECRET_KEY` | Ключ подписи Flask-сессий (`openssl rand -hex 16`) | *Автогенерация* |
| `NODE_API_TOKEN` | Уникальный токен нод для доступа к API (`openssl rand -hex 16`) | *Автогенерация* |
| `ADMIN_PASSWORD` | Стартовый пароль администратора при первой инициализации | `admin123` |

---

## 🚀 Варианты развертывания

### Вариант 1. Запуск через Docker (Рекомендуемый)

Самый быстрый способ развернуть сервер в изолированном контейнере с сохранением данных на хосте.

1. **Клонирование проекта:**
   ```bash
   git clone https://github.com/Ttolyanich/centralized-auth.git /opt/centralized-auth
   cd /opt/centralized-auth
   ```
2. **Создание и настройка `.env`:**
   ```bash
   cp .env.example .env
   # Отредактируйте .env, прописав сгенерированные SECRET_KEY и NODE_API_TOKEN
   nano .env
   ```
3. **Запуск контейнера:**
   ```bash
   docker compose up -d
   ```

### Вариант 2. Нативный запуск (через Systemd)

1. Установите зависимости:
   ```bash
   pip3 install -r requirements.txt
   ```
2. Выполните первый запуск для генерации файлов конфигурации и создания базы данных:
   ```bash
   python3 app.py
   ```
3. Настройте службу systemd:
   ```bash
   sudo cp centralized-auth.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now centralized-auth
   ```

---

## 🤖 API Интеграция для нод

### Проверка авторизации
Используется удаленными нодами (например, `openvpn-web`) для проверки логина и пароля.

* **URL:** `POST /api/auth/verify`
* **Заголовки:**
  * `Content-Type: application/json`
  * `X-Node-Token: <ВАШ_NODE_API_TOKEN>`
* **Тело запроса:**
  ```json
  {
    "username": "admin",
    "password": "user_password"
  }
  ```
* **Ответ (Успешно):**
  ```json
  {
    "success": true,
    "role": "admin"
  }
  ```
* **Ответ (Ошибка):**
  ```json
  {
    "success": false,
    "error": "Неверный логин или пароль"
  }
  ```
