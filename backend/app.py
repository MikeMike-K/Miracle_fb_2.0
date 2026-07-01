import os
import sqlite3
import smtplib
import datetime
from copy import deepcopy
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from functools import wraps

from flask import Flask, request, session, jsonify, make_response
from werkzeug.security import generate_password_hash, check_password_hash
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'super_secret_key_change_me')

# CORS для фронтенда (cookie-сессия). Без Flask-CORS — он давал 500 на всех запросах.
_DEFAULT_LOCAL_ORIGINS = (
    'http://localhost:8081',
    'http://127.0.0.1:8081',
    'http://localhost:8080',
    'http://127.0.0.1:8080',
)
_raw_frontend_origin = os.environ.get('FRONTEND_ORIGIN', ','.join(_DEFAULT_LOCAL_ORIGINS))
if _raw_frontend_origin.strip() == '*':
    cors_origins = set(_DEFAULT_LOCAL_ORIGINS)
else:
    cors_origins = {o.strip() for o in _raw_frontend_origin.split(',') if o.strip()}
if not cors_origins:
    cors_origins = set(_DEFAULT_LOCAL_ORIGINS)


def _is_local_dev_origin(origin):
    """Локально разрешаем любой порт на localhost / 127.0.0.1 (serve.py может взять 8081+)."""
    if os.environ.get('DATABASE_URL') or not origin:
        return False
    from urllib.parse import urlparse
    parsed = urlparse(origin)
    return parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1')


def _origin_allowed(origin):
    return origin in cors_origins or _is_local_dev_origin(origin)


def _cors_headers(response):
    origin = request.headers.get('Origin')
    if origin and _origin_allowed(origin):
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers.add('Vary', 'Origin')
    return response


@app.before_request
def cors_preflight():
    if request.method != 'OPTIONS':
        return None
    response = make_response('', 204)
    origin = request.headers.get('Origin')
    if origin and _origin_allowed(origin):
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = request.headers.get(
            'Access-Control-Request-Headers', 'Content-Type'
        )
        response.headers.add('Vary', 'Origin')
    return response


@app.after_request
def cors_after_request(response):
    return _cors_headers(response)

# SameSite=None требует Secure (HTTPS); для локального HTTP используем Lax.
_session_secure = os.environ.get('SESSION_COOKIE_SECURE', '0') == '1'
app.config['SESSION_COOKIE_SAMESITE'] = 'None' if _session_secure else 'Lax'
app.config['SESSION_COOKIE_SECURE'] = _session_secure

# Определяем, где запущен код: на Railway (PostgreSQL) или локально (SQLite)
DATABASE_URL = os.environ.get('DATABASE_URL')

if DATABASE_URL:
    import psycopg2
    DB_TYPE = 'postgresql'
    DB_NAME = DATABASE_URL
else:
    DB_TYPE = 'sqlite'
    DB_NAME = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'database.db')


def get_db_connection():
    """Умная функция подключения: PostgreSQL на Railway, SQLite локально"""
    if DB_TYPE == 'postgresql':
        conn = psycopg2.connect(DB_NAME)

        class PGWrapper:
            def __init__(self, conn):
                self.conn = conn
                self._cursor = conn.cursor()

            def execute(self, query, params=()):
                pg_query = query.replace('?', '%s')
                self._cursor.execute(pg_query, params)
                return self

            def fetchone(self):
                return self._cursor.fetchone()

            def fetchall(self):
                return self._cursor.fetchall()

            @property
            def lastrowid(self):
                self._cursor.execute("SELECT lastval()")
                return self._cursor.fetchone()[0]

            def commit(self):
                self.conn.commit()

            def close(self):
                self._cursor.close()
                self.conn.close()

            def cursor(self):
                return self

            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.close()

        return PGWrapper(conn)
    else:
        conn = sqlite3.connect(DB_NAME)
        return conn


DEFAULT_ADMIN_LOGIN = 'admin'
DEFAULT_ADMIN_PASSWORD = 'admin123'

scheduler = BackgroundScheduler(timezone='Europe/Moscow')
if os.environ.get('RENDER') is None and 'pythonanywhere' not in os.environ.get('SERVER_SOFTWARE', '').lower():
    try:
        scheduler.start()
    except Exception as e:
        print(f"[SCHEDULER] Не удалось запустить: {e}")


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                      (id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT, role TEXT,
                       first_name TEXT, last_name TEXT, patronymic TEXT, email TEXT)''')
    cursor.execute("SELECT * FROM users WHERE username = ?", (DEFAULT_ADMIN_LOGIN,))
    if not cursor.fetchone():
        cursor.execute('''INSERT INTO users (username, password, role, first_name, last_name, patronymic, email) 
                          VALUES (?, ?, ?, ?, ?, ?, ?)''',
                       (DEFAULT_ADMIN_LOGIN, generate_password_hash(DEFAULT_ADMIN_PASSWORD), 'admin',
                        'Главный', 'Администратор', '', 'admin@miracle.local'))

    cursor.execute('''CREATE TABLE IF NOT EXISTS clients 
                      (id INTEGER PRIMARY KEY, last_name TEXT, first_name TEXT, patronymic TEXT, 
                       dob TEXT, description TEXT, phone TEXT, email TEXT, position TEXT)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS companies 
                      (id INTEGER PRIMARY KEY, name TEXT, country TEXT, activity TEXT, 
                       type TEXT, website TEXT, description TEXT)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS company_employees 
                      (id INTEGER PRIMARY KEY, company_id INTEGER, client_id INTEGER, status TEXT DEFAULT 'РАБОТАЕТ',
                       FOREIGN KEY(company_id) REFERENCES companies(id), 
                       FOREIGN KEY(client_id) REFERENCES clients(id))''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS events 
                      (id INTEGER PRIMARY KEY, company_id INTEGER, project_id INTEGER, client_id INTEGER, event_type TEXT, 
                       start_date TEXT, end_date TEXT, responsible_user TEXT, 
                       description TEXT, status TEXT DEFAULT 'planned',
                       result TEXT, completion_desc TEXT, rating INTEGER)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS projects 
                      (id INTEGER PRIMARY KEY, name TEXT, project_type TEXT, status TEXT, 
                       end_date TEXT, area TEXT, address TEXT, budget TEXT, cp_amount TEXT,
                       region TEXT, currency TEXT DEFAULT 'RUB')''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS project_companies 
                      (id INTEGER PRIMARY KEY, project_id INTEGER, company_id INTEGER,
                       FOREIGN KEY(project_id) REFERENCES projects(id),
                       FOREIGN KEY(company_id) REFERENCES companies(id),
                       UNIQUE(project_id, company_id))''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS report_settings 
                      (id INTEGER PRIMARY KEY, recipient_ids TEXT, frequency TEXT, 
                       day_value INTEGER, time_value TEXT)''')

    conn.commit()
    _migrate_schema(conn)
    conn.close()


def _add_column_if_missing(cursor, table, column, col_def):
    cursor.execute(f'PRAGMA table_info({table})')
    if column not in [row[1] for row in cursor.fetchall()]:
        cursor.execute(f'ALTER TABLE {table} ADD COLUMN {column} {col_def}')


def _migrate_schema(conn):
    cursor = conn.cursor()
    _add_column_if_missing(cursor, 'projects', 'region', 'TEXT')
    _add_column_if_missing(cursor, 'projects', 'currency', "TEXT DEFAULT 'RUB'")
    conn.commit()


def _normalize_website(website):
    website = (website or '').strip()
    if not website:
        return ''
    lower = website.lower()
    if not lower.startswith(('http://', 'https://')):
        website = f'https://{website}'
    return website


def _validate_company_payload(data):
    website = _normalize_website(data.get('website'))
    if not website:
        return 'Укажите ссылку на сайт компании', None
    return None, website


def _validate_project_payload(data):
    address = (data.get('address') or '').strip()
    region = (data.get('region') or '').strip()
    if not address:
        return 'Укажите адрес проекта'
    if not region:
        return 'Выберите регион проекта'
    return None


init_db()


# ================= SMTP =================
SMTP_ACCOUNTS = [
    {'id': 'yandex', 'email': 'Mikele208ID@yandex.ru', 'server': 'smtp.yandex.ru', 'ssl_port': 465, 'starttls_port': 587},
    {'id': 'mailru', 'email': 'mikemike_000@mail.ru', 'server': 'smtp.mail.ru', 'ssl_port': 465, 'starttls_port': 587},
    {'id': 'gmail', 'email': 'mkachin9@gmail.com', 'server': 'smtp.gmail.com', 'ssl_port': 465, 'starttls_port': 587},
]

SMTP_PASSWORDS = {
    'yandex': os.environ.get('SMTP_PASSWORD_YANDEX', '').strip(),
    'mailru': os.environ.get('SMTP_PASSWORD_MAILRU', '').strip(),
    'gmail': os.environ.get('SMTP_PASSWORD_GMAIL', '').strip(),
}


def _smtp_accounts_status():
    return [{
        'id': a['id'],
        'email': a['email'],
        'configured': bool(SMTP_PASSWORDS.get(a['id']))
    } for a in SMTP_ACCOUNTS]


def _smtp_check_accounts():
    """Проверка логина SMTP по всем аккаунтам (без отправки письма)."""
    timeout = int(os.environ.get('SMTP_TIMEOUT', 20))
    checks = []

    for account in SMTP_ACCOUNTS:
        password = SMTP_PASSWORDS.get(account['id'], '')
        if not password:
            checks.append({
                'id': account['id'],
                'email': account['email'],
                'ok': False,
                'message': 'Пароль не задан',
            })
            continue

        last_error = ''
        for mode, port in (('ssl', account['ssl_port']), ('starttls', account['starttls_port'])):
            try:
                if mode == 'ssl':
                    with smtplib.SMTP_SSL(account['server'], port, timeout=timeout) as server:
                        server.login(account['email'], password)
                else:
                    with smtplib.SMTP(account['server'], port, timeout=timeout) as server:
                        server.ehlo()
                        server.starttls()
                        server.ehlo()
                        server.login(account['email'], password)
                checks.append({
                    'id': account['id'],
                    'email': account['email'],
                    'ok': True,
                    'message': f'OK ({mode}:{port})',
                })
                last_error = ''
                break
            except Exception as e:
                last_error = f'{mode}:{port} — {e}'

        if last_error:
            checks.append({
                'id': account['id'],
                'email': account['email'],
                'ok': False,
                'message': last_error,
            })

    return checks


def _send_smtp_message(msg):
    """
    Отправка письма через один из фиксированных SMTP-аккаунтов.
    Пароли задаются вручную из админки и хранятся только в памяти процесса.
    """
    timeout = int(os.environ.get('SMTP_TIMEOUT', 20))
    errors = []
    configured_accounts = [a for a in SMTP_ACCOUNTS if SMTP_PASSWORDS.get(a['id'])]

    if not configured_accounts:
        raise ConnectionError('Не задан ни один SMTP-пароль. Заполните пароли в настройках отчетов.')

    for account in configured_accounts:
        password = SMTP_PASSWORDS.get(account['id'], '')
        for mode, port in (('ssl', account['ssl_port']), ('starttls', account['starttls_port'])):
            try:
                msg_copy = deepcopy(msg)
                if msg_copy.get('From'):
                    msg_copy.replace_header('From', account['email'])
                else:
                    msg_copy['From'] = account['email']

                if mode == 'ssl':
                    with smtplib.SMTP_SSL(account['server'], port, timeout=timeout) as server:
                        server.login(account['email'], password)
                        server.send_message(msg_copy)
                else:
                    with smtplib.SMTP(account['server'], port, timeout=timeout) as server:
                        server.ehlo()
                        server.starttls()
                        server.ehlo()
                        server.login(account['email'], password)
                        server.send_message(msg_copy)
                return account['email']
            except Exception as e:
                errors.append(f"{account['email']} {mode}:{port} — {e}")

    hint = (
        'Не удалось отправить письмо через все аккаунты. '
        'Проверьте пароли приложений и доступ SMTP (465/587).'
    )
    raise ConnectionError(f'{hint} Детали: {"; ".join(errors)}')


# ================= ФУНКЦИИ ОТПРАВКИ ОТЧЕТОВ =================
def _resolve_recipient_ids(cursor, db_id, override=None):
    """Получатели из override (тест/форма) или из report_settings."""
    if override is not None:
        ids = [str(r).strip() for r in override if str(r).strip()]
        return ids
    settings = cursor.execute(
        "SELECT recipient_ids FROM report_settings WHERE id = ?", (db_id,)
    ).fetchone()
    if not settings or not settings[0]:
        return []
    return [x.strip() for x in settings[0].split(',') if x.strip()]


def _normalize_recipient_ids(raw_recipients):
    normalized = []
    seen = set()
    for r in raw_recipients or []:
        s = str(r).strip()
        if not s or not s.isdigit():
            continue
        if s in seen:
            continue
        seen.add(s)
        normalized.append(s)
    return normalized


def _is_valid_time_value(time_value):
    if not isinstance(time_value, str) or len(time_value) != 5 or time_value[2] != ':':
        return False
    hh, mm = time_value.split(':')
    if not (hh.isdigit() and mm.isdigit()):
        return False
    h, m = int(hh), int(mm)
    return 0 <= h <= 23 and 0 <= m <= 59


def _scheduler_snapshot():
    snap = []
    for job in scheduler.get_jobs():
        snap.append({
            'id': job.id,
            'next_run': job.next_run_time.isoformat() if job.next_run_time else None
        })
    return snap


DEMO_TAG = '[DEMO]'
REPORT_EVENT_TYPES = [
    "М2. Звонок/Письмо", "М3. Встреча с клиентом", "М4. Встреча с партнером",
    "М5. Получение запроса КП", "М6. Изменение запроса КП", "М7. Отправка КП",
    "М7.1. Повторная отправка КП", "М8. Получение заказа",
]
EVENT_RESULTS = [
    'R1. Назначен звонок',
    'R2. Назначена встреча',
    'R3. Назначен запрос КП',
    'No way',
]


def _validate_finish_payload(data):
    result = (data.get('result') or '').strip()
    if result not in EVENT_RESULTS:
        return f'Выберите результат из списка: {", ".join(EVENT_RESULTS)}'
    try:
        rating = int(data.get('rating', 0))
    except (TypeError, ValueError):
        return 'Укажите оценку от 1 до 5'
    if rating < 1 or rating > 5:
        return 'Укажите оценку от 1 до 5'
    return None
DEMO_CLIENTS = [
    'ООО «СеверСтрой»', 'АО «ТехноПарк»', 'ЗАО «МегаТорг»', 'ИП Иванов',
    'ООО «СтройГрад»', 'АО «ЭнергоМаш»',
]


def _insert_demo_event(cursor, username, dt, status, event_type, description,
                       result='', completion_desc='', rating=0,
                       company_id=None, project_id=None, client_id=None):
    date_str = dt.strftime('%Y-%m-%d')
    cursor.execute('''
        INSERT INTO events (company_id, project_id, client_id, event_type, start_date, end_date,
            responsible_user, description, status, result, completion_desc, rating)
        VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?)
    ''', (company_id, project_id, client_id, event_type, date_str, username, description, status,
          result or '', completion_desc or '', rating or 0))


def seed_demo_report_events():
    """Тестовые мероприятия для проверки отчётов (пометка [DEMO], можно пересоздавать)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.datetime.now()

    users = cursor.execute(
        "SELECT username, first_name, last_name, role FROM users WHERE role != 'admin'"
    ).fetchall()
    if not users:
        users = cursor.execute("SELECT username, first_name, last_name, role FROM users").fetchall()
    if not users:
        conn.close()
        return {'success': False, 'error': 'В базе нет пользователей', 'created': 0, 'deleted': 0, 'users': 0}

    company = cursor.execute("SELECT id, name FROM companies LIMIT 1").fetchone()
    project = cursor.execute("SELECT id, name FROM projects LIMIT 1").fetchone()
    company_id = company[0] if company else None
    project_id = project[0] if project else None

    cursor.execute("DELETE FROM events WHERE description LIKE ?", (f'{DEMO_TAG}%',))
    deleted = cursor.rowcount
    created = 0

    for idx, (username, first_name, last_name, role) in enumerate(users):
        label = f"{first_name} {last_name}".strip() or username
        primary_type = REPORT_EVENT_TYPES[idx % len(REPORT_EVENT_TYPES)]

        # 6 выполненных мероприятий одного типа — для таблицы детализации с описаниями
        for n in range(6):
            client = DEMO_CLIENTS[(idx + n) % len(DEMO_CLIENTS)]
            dt = now - datetime.timedelta(days=6 - n)
            desc = (f'{DEMO_TAG} {primary_type}: {client} — обсуждение условий поставки, '
                    f'контактное лицо {label}, встреча №{n + 1}')
            results = EVENT_RESULTS
            comments = [
                f'Клиент {client} запросил уточнение по срокам. Ответственный: {label}.',
                f'Отправлено коммерческое предложение в {client}.',
                f'Проведена встреча в офисе {client}, зафиксированы требования.',
                f'Согласованы технические параметры с {client}.',
                f'Получена обратная связь от {client}, оценка работы высокая.',
                f'Запланирован повторный контакт с {client} на следующей неделе.',
            ]
            _insert_demo_event(
                cursor, username, dt, 'completed', primary_type, desc,
                result=results[n % len(results)], completion_desc=comments[n], rating=3 + (n % 3),
                company_id=company_id, project_id=project_id if not company_id else None)
            created += 1

        # Несколько запланированных того же типа в отчётном периоде (для столбца «План»)
        for n in range(3):
            dt = now - datetime.timedelta(days=2 - n)
            desc = f'{DEMO_TAG} {primary_type}: плановый контакт №{n + 1} ({label})'
            _insert_demo_event(
                cursor, username, dt, 'planned', primary_type, desc,
                company_id=company_id, project_id=project_id if not company_id else None)
            created += 1

        # План на следующий период — по 2 мероприятия других типов
        for t_off, etype in enumerate(REPORT_EVENT_TYPES):
            if etype == primary_type:
                continue
            if t_off > 4:
                break
            dt = now + datetime.timedelta(days=2 + t_off)
            desc = f'{DEMO_TAG} {etype}: запланировано на след. период ({label})'
            _insert_demo_event(
                cursor, username, dt, 'planned', etype, desc,
                company_id=company_id, project_id=project_id if not company_id else None)
            created += 1

        # Сегодня — для ежедневного плана (2–3 мероприятия)
        for n in range(2 + (idx % 2)):
            etype = REPORT_EVENT_TYPES[(idx + n + 1) % len(REPORT_EVENT_TYPES)]
            client = DEMO_CLIENTS[(idx + n) % len(DEMO_CLIENTS)]
            desc = f'{DEMO_TAG} {etype}: план на сегодня — {client} ({label})'
            _insert_demo_event(
                cursor, username, now, 'planned', etype, desc,
                company_id=company_id, project_id=project_id if not company_id else None)
            created += 1

        # Разнообразие по другим типам — выполненные с описанием
        for n, etype in enumerate(REPORT_EVENT_TYPES[:3]):
            if etype == primary_type:
                continue
            dt = now - datetime.timedelta(days=4 + n)
            client = DEMO_CLIENTS[(idx + n + 2) % len(DEMO_CLIENTS)]
            desc = f'{DEMO_TAG} {etype}: {client} — краткий отчёт ({label})'
            _insert_demo_event(
                cursor, username, dt, 'completed', etype, desc,
                result=EVENT_RESULTS[n % len(EVENT_RESULTS)],
                completion_desc=f'Итог работы с {client}: положительный отклик.',
                rating=4, company_id=company_id, project_id=project_id if not company_id else None)
            created += 1

    conn.commit()
    conn.close()
    return {
        'success': True,
        'created': created,
        'deleted': deleted,
        'users': len(users),
        'company': company[1] if company else None,
        'project': project[1] if project else None,
    }


def build_report_html(report_type='weekly'):
    """Собирает HTML еженедельного/ежемесячного отчёта без отправки почты."""
    if report_type not in ('weekly', 'monthly'):
        raise ValueError('report_type must be weekly or monthly')

    conn = get_db_connection()
    cursor = conn.cursor()

    now = datetime.datetime.now()
    if report_type == 'weekly':
        period_end = now
        period_start = now - datetime.timedelta(days=7)
        next_period_end = now + datetime.timedelta(days=7)
        next_period_start = now
        period_name = "ЕЖЕНЕДЕЛЬНЫЙ ОТЧЕТ / WEEKLY REPORT"
    else:
        period_end = now
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        next_period_end = now + datetime.timedelta(days=30)
        next_period_start = now
        period_name = "ЕЖЕМЕСЯЧНЫЙ ОТЧЕТ / MONTHLY REPORT"

    period_start_str = period_start.strftime("%d.%m.%Y %H:%M")
    period_end_str = period_end.strftime("%d.%m.%Y %H:%M")
    next_period_start_str = next_period_start.strftime("%d.%m.%Y")
    next_period_end_str = next_period_end.strftime("%d.%m.%Y")

    cursor.execute("SELECT username, first_name, last_name, patronymic, role FROM users WHERE role != 'admin'")
    users = cursor.fetchall()

    event_types_list = [
        "М2. Звонок/Письмо", "М3. Встреча с клиентом", "М4. Встреча с партнером",
        "М5. Получение запроса КП", "М6. Изменение запроса КП", "М7. Отправка КП",
        "М7.1. Повторная отправка КП", "М8. Получение заказа"
    ]

    cursor.execute('''
        SELECT responsible_user, status, event_type, start_date, description, result, completion_desc
        FROM events WHERE date(start_date) >= date(?) AND date(start_date) <= date(?)
        ORDER BY responsible_user, event_type, start_date
    ''', (period_start.strftime("%Y-%m-%d"), period_end.strftime("%Y-%m-%d")))
    past_events = cursor.fetchall()

    cursor.execute('''
        SELECT responsible_user, event_type, start_date, description
        FROM events WHERE status = 'planned' AND date(start_date) >= date(?) AND date(start_date) <= date(?)
        ORDER BY responsible_user, event_type, start_date
    ''', (next_period_start.strftime("%Y-%m-%d"), next_period_end.strftime("%Y-%m-%d")))
    future_events = cursor.fetchall()

    cursor.execute('''
        SELECT start_date, event_type, responsible_user, description, result, completion_desc
        FROM events WHERE status = 'completed' AND date(start_date) >= date(?) AND date(start_date) <= date(?)
        ORDER BY start_date DESC
    ''', (period_start.strftime("%Y-%m-%d"), period_end.strftime("%Y-%m-%d")))
    completed_events_detail = cursor.fetchall()

    conn.close()

    user_data = {}
    for u in users:
        username = u[0]
        name = f"{u[1]} {u[2]}".strip() or username
        user_data[username] = {
            'name': name,
            'stats': {et: {'planned': [], 'completed': [], 'next_planned': []} for et in event_types_list}
        }

    for ev in past_events:
        resp = ev[0] or "Не назначен"
        if resp not in user_data:
            user_data[resp] = {'name': resp,
                               'stats': {et: {'planned': [], 'completed': [], 'next_planned': []} for et in
                                         event_types_list}}
        status, etype, date, desc = ev[1], ev[2], ev[3], ev[4]
        if etype in user_data[resp]['stats']:
            event_str = f"{date}: {desc}" if desc else f"{date}"
            if status == 'planned':
                user_data[resp]['stats'][etype]['planned'].append(event_str)
            elif status == 'completed':
                user_data[resp]['stats'][etype]['completed'].append(event_str)

    for ev in future_events:
        resp = ev[0] or "Не назначен"
        if resp not in user_data:
            user_data[resp] = {'name': resp,
                               'stats': {et: {'planned': [], 'completed': [], 'next_planned': []} for et in
                                         event_types_list}}
        etype, date, desc = ev[1], ev[2], ev[3]
        if etype in user_data[resp]['stats']:
            event_str = f"({date}) {desc}" if desc else f"({date})"
            user_data[resp]['stats'][etype]['next_planned'].append(event_str)

    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #0F172A; background-color: #F8FAFC; padding: 20px; margin: 0;">
        <div style="max-width: 900px; margin: 0 auto; background: #FFFFFF; padding: 30px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
            <h2 style="color: #1E3A8A; text-align: center; border-bottom: 2px solid #38BDF8; padding-bottom: 10px; margin-top: 0;">{period_name}</h2>
            <p style="text-align: center; font-size: 1.1em; color: #64748B; margin-bottom: 30px;">
                За период <strong>{period_start_str}</strong> - <strong>{period_end_str}</strong>
            </p>
            <h3 style="color: #0F172A; border-left: 4px solid #F97316; padding-left: 10px;">1. Статистика и план за отчетный период</h3>
    """

    for username, data in sorted(user_data.items()):
        html += f"""
            <div style="margin-top: 30px; margin-bottom: 20px; page-break-inside: avoid;">
                <h4 style="color: #1E3A8A; margin-bottom: 10px; background: #F1F5F9; padding: 8px; border-radius: 4px;">
                    Менеджер по продажам / Sales manager: {data['name']}
                </h4>
                <table style="border-collapse: collapse; width: 100%; font-size: 0.85em; border: 1px solid #CBD5E1;">
                    <thead>
                        <tr style="background-color: #E2E8F0;">
                            <th style="border: 1px solid #CBD5E1; padding: 8px; width: 20%; text-align: left;">Вид мероприятия</th>
                            <th style="border: 1px solid #CBD5E1; padding: 8px; width: 26%; text-align: left;">План за отчетный период</th>
                            <th style="border: 1px solid #CBD5E1; padding: 8px; width: 26%; text-align: left;">Факт за отчетный период</th>
                            <th style="border: 1px solid #CBD5E1; padding: 8px; width: 28%; text-align: left;">План на след. период ({next_period_start_str} - {next_period_end_str})</th>
                        </tr>
                    </thead>
                    <tbody>
        """
        for etype in event_types_list:
            stats = data['stats'][etype]
            planned_count = len(stats['planned'])
            completed_count = len(stats['completed'])
            next_planned_count = len(stats['next_planned'])

            planned_list = "<br>".join(
                [f"• {item}" for item in stats['planned']]) or "<span style='color:#94A3B8'>-</span>"
            completed_list = "<br>".join(
                [f"• {item}" for item in stats['completed']]) or "<span style='color:#94A3B8'>-</span>"
            next_planned_list = "<br>".join(
                [f"• {item}" for item in stats['next_planned']]) or "<span style='color:#94A3B8'>-</span>"

            html += f"""
                        <tr>
                            <td style="border: 1px solid #CBD5E1; padding: 8px; vertical-align: top;"><strong>{etype}</strong></td>
                            <td style="border: 1px solid #CBD5E1; padding: 8px; vertical-align: top;">
                                <strong style="color: #2563EB;">{planned_count}</strong><br>
                                <span style="color: #64748B; font-size: 0.9em;">{planned_list}</span>
                            </td>
                            <td style="border: 1px solid #CBD5E1; padding: 8px; vertical-align: top;">
                                <strong style="color: #059669;">{completed_count}</strong><br>
                                <span style="color: #64748B; font-size: 0.9em;">{completed_list}</span>
                            </td>
                            <td style="border: 1px solid #CBD5E1; padding: 8px; vertical-align: top;">
                                <strong style="color: #D97706;">{next_planned_count}</strong><br>
                                <span style="color: #64748B; font-size: 0.9em;">{next_planned_list}</span>
                            </td>
                        </tr>
            """
        html += """
                    </tbody>
                </table>
            </div>
        """

    html += """
            <h3 style="color: #0F172A; border-left: 4px solid #10B981; padding-left: 10px; margin-top: 40px;">2. Детализация по выполненным мероприятиям за отчетный период</h3>
            <table style="border-collapse: collapse; width: 100%; font-size: 0.85em; border: 1px solid #CBD5E1; margin-top: 15px;">
                <thead>
                    <tr style="background-color: #E2E8F0;">
                        <th style="border: 1px solid #CBD5E1; padding: 8px; width: 12%;">Дата исполнения</th>
                        <th style="border: 1px solid #CBD5E1; padding: 8px; width: 18%;">Вид</th>
                        <th style="border: 1px solid #CBD5E1; padding: 8px; width: 20%;">Исполнитель / Ответственный</th>
                        <th style="border: 1px solid #CBD5E1; padding: 8px; width: 25%;">Название / Описание</th>
                        <th style="border: 1px solid #CBD5E1; padding: 8px; width: 25%;">Результат</th>
                    </tr>
                </thead>
                <tbody>
    """

    if completed_events_detail:
        for ev in completed_events_detail:
            date = ev[0]
            etype = ev[1]
            resp = ev[2] or "Не назначен"
            desc = ev[3] or "Без описания"
            result = ev[4] or "Не указан"
            comp_desc = ev[5]

            result_str = f"<strong style='color: #059669;'>{result}</strong>"
            if comp_desc:
                result_str += f"<br><span style='color: #64748B; font-size: 0.9em;'>{comp_desc}</span>"

            resp_name = resp
            for u in users:
                if u[0] == resp:
                    resp_name = f"{u[1]} {u[2]}".strip() or resp
                    break

            html += f"""
                    <tr>
                        <td style="border: 1px solid #CBD5E1; padding: 8px; vertical-align: top;">{date}</td>
                        <td style="border: 1px solid #CBD5E1; padding: 8px; vertical-align: top;">{etype}</td>
                        <td style="border: 1px solid #CBD5E1; padding: 8px; vertical-align: top;">{resp_name}</td>
                        <td style="border: 1px solid #CBD5E1; padding: 8px; vertical-align: top;">{desc}</td>
                        <td style="border: 1px solid #CBD5E1; padding: 8px; vertical-align: top;">{result_str}</td>
                    </tr>
            """
    else:
        html += """
                    <tr>
                        <td colspan="5" style="border: 1px solid #CBD5E1; padding: 15px; text-align: center; color: #64748B;">
                            За отчетный период нет выполненных мероприятий.
                        </td>
                    </tr>
        """

    html += """
                </tbody>
            </table>
            <p style="margin-top: 40px; color: #94A3B8; font-size: 12px; text-align: center; border-top: 1px solid #E2E8F0; padding-top: 15px;">
                С уважением, автоматическая система Miracle_2.0<br>
                Дата формирования: """ + datetime.datetime.now().strftime('%d.%m.%Y %H:%M') + """
            </p>
        </div>
    </body>
    </html>
    """

    return html, period_name


def send_report_email(report_type='weekly', recipient_ids_override=None):
    print(f"\n{'=' * 60}\n[DEBUG] Запуск отправки: {report_type.upper()}\n{'=' * 60}")
    conn = get_db_connection()
    cursor = conn.cursor()

    db_id = 1 if report_type == 'weekly' else 2
    recipient_ids = _resolve_recipient_ids(cursor, db_id, recipient_ids_override)
    if not recipient_ids:
        print("[DEBUG] ОШИБКА: Нет получателей для этого типа отчета.")
        conn.close()
        return False

    placeholders = ','.join('?' * len(recipient_ids))
    recipients = cursor.execute(f"SELECT email FROM users WHERE id IN ({placeholders})", recipient_ids).fetchall()
    emails_to_send = [r[0] for r in recipients if r[0]]

    if not emails_to_send:
        print("[DEBUG] ОШИБКА: У получателей не указана почта.")
        conn.close()
        return False

    conn.close()

    try:
        html, period_name = build_report_html(report_type)
        msg = MIMEMultipart()
        msg['To'] = ", ".join(emails_to_send)
        msg['Subject'] = period_name
        msg.attach(MIMEText(html, 'html'))
        sent_from = _send_smtp_message(msg)
        print(f"УСПЕХ: {report_type} отчет отправлен на {', '.join(emails_to_send)} (через {sent_from})")
        return True
    except Exception as e:
        print(f"ОШИБКА ОТПРАВКИ: {e}")
        return False


def build_daily_plan_html(cursor, username, first_name, last_name, test_mode=False):
    """HTML ежедневного плана для одного пользователя."""
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    today_display = datetime.datetime.now().strftime("%d.%m.%Y")
    full_name = f"{first_name} {last_name}".strip() or username

    cursor.execute('''
        SELECT event_type, start_date, description, company_id, project_id, client_id
        FROM events 
        WHERE responsible_user = ? AND status = 'planned' AND date(start_date) = ?
        ORDER BY start_date
    ''', (username, today_str))
    events = cursor.fetchall()

    subject_prefix = "[ТЕСТ] " if test_mode else ""
    subject = f"{subject_prefix}Ваш план мероприятий на {today_display}"

    html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; color: #0F172A; background-color: #F8FAFC; padding: 20px; margin: 0;">
            <div style="max-width: 600px; margin: 0 auto; background: #FFFFFF; padding: 25px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
                <h2 style="color: #1E3A8A; border-bottom: 2px solid #38BDF8; padding-bottom: 10px; margin-top: 0;">Добрый день, {full_name}!</h2>
                <p style="font-size: 1.1em; color: #64748B;">Направляем вам список запланированных мероприятий на сегодня (<strong>{today_display}</strong>):</p>
        """

    if events:
        html_body += '<ul style="line-height: 1.6; color: #334155;">'
        for ev in events:
            etype, date, desc, comp_id, proj_id, client_id = ev
            context = ""
            if comp_id:
                comp_name = cursor.execute("SELECT name FROM companies WHERE id = ?", (comp_id,)).fetchone()
                context = f" (Компания: {comp_name[0]})" if comp_name else ""
            elif proj_id:
                proj_name = cursor.execute("SELECT name FROM projects WHERE id = ?", (proj_id,)).fetchone()
                context = f" (Проект: {proj_name[0]})" if proj_name else ""

            desc_text = f"<br><small style='color: #64748B;'>{desc}</small>" if desc else ""
            html_body += f"<li style='margin-bottom: 15px;'><strong>{etype}</strong>{context}{desc_text}</li>"
        html_body += '</ul>'
    else:
        html_body += "<p style='color: #059669; font-weight: bold; background: #ECFDF5; padding: 15px; border-radius: 6px;'>На сегодня новых мероприятий не запланировано. Отличного дня!</p>"

    html_body += """
                <p style="margin-top: 30px; color: #94A3B8; font-size: 12px; border-top: 1px solid #E2E8F0; padding-top: 15px; text-align: center;">
                    С уважением, автоматическая система Miracle_2.0
                </p>
            </div>
        </body>
        </html>
        """

    return html_body, subject, full_name


def send_daily_plan_email(test_mode=False, recipient_ids_override=None):
    print(f"\n{'=' * 60}\n[DEBUG] Запуск отправки ежедневного плана (Тест: {test_mode})\n{'=' * 60}")
    conn = get_db_connection()
    cursor = conn.cursor()

    recipient_ids = _resolve_recipient_ids(cursor, 3, recipient_ids_override)
    if not recipient_ids:
        print("[DEBUG] ОШИБКА: Нет получателей для ежедневного плана.")
        conn.close()
        return False

    placeholders = ','.join('?' * len(recipient_ids))

    users = cursor.execute(f"SELECT id, username, first_name, last_name, email FROM users WHERE id IN ({placeholders})",
                           recipient_ids).fetchall()

    success_count = 0
    for user in users:
        user_id, username, first_name, last_name, email = user
        if not email:
            continue

        html_body, subject, full_name = build_daily_plan_html(
            cursor, username, first_name, last_name, test_mode=test_mode)

        try:
            msg = MIMEMultipart()
            msg['To'] = email
            msg['Subject'] = subject
            msg.attach(MIMEText(html_body, 'html'))
            sent_from = _send_smtp_message(msg)

            print(f"Письмо отправлено: {full_name} ({email}) через {sent_from}")
            success_count += 1
        except Exception as e:
            print(f"Ошибка отправки для {full_name}: {e}")

    conn.close()
    print(f"[DEBUG] Всего успешно отправлено: {success_count} из {len(users)}")
    return success_count > 0


def update_scheduler():
    scheduler.remove_all_jobs()
    conn = get_db_connection()
    weekly = conn.cursor().execute(
        "SELECT recipient_ids, day_value, time_value FROM report_settings WHERE id = 1").fetchone()
    monthly = conn.cursor().execute(
        "SELECT recipient_ids, day_value, time_value FROM report_settings WHERE id = 2").fetchone()
    daily = conn.cursor().execute(
        "SELECT recipient_ids, time_value FROM report_settings WHERE id = 3").fetchone()
    conn.close()

    if weekly and weekly[0]:
        day_int = int(weekly[1])
        hour, minute = map(int, weekly[2].split(':'))
        scheduler.add_job(send_report_email, 'cron', day_of_week=day_int, hour=hour, minute=minute, args=['weekly'],
                          id='weekly_report', timezone='Europe/Moscow')

    if monthly and monthly[0]:
        day_int = int(monthly[1])
        if day_int < 1: day_int = 1
        hour, minute = map(int, monthly[2].split(':'))
        scheduler.add_job(send_report_email, 'cron', day=day_int, hour=hour, minute=minute, args=['monthly'],
                          id='monthly_report', timezone='Europe/Moscow')

    if daily and daily[0]:
        hour, minute = map(int, daily[1].split(':'))
        print(f"[SCHEDULER] Ежедневный план: каждый день в {hour:02d}:{minute:02d} (МСК)")
        scheduler.add_job(send_daily_plan_email, 'cron', hour=hour, minute=minute, id='daily_plan',
                          timezone='Europe/Moscow')

    print(f"[SCHEDULER] Активные задачи: {[job.id for job in scheduler.get_jobs()]}")


update_scheduler()


# ================= ВСПОМОГАТЕЛЬНОЕ =================
def login_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if 'logged_in' not in session:
            return jsonify({'error': 'Требуется авторизация'}), 401
        return f(*args, **kwargs)
    return wrap


def admin_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if session.get('role') not in ['admin', 'local_admin']:
            return jsonify({'error': 'Недостаточно прав'}), 403
        return f(*args, **kwargs)
    return wrap


ADMIN_ROLES = frozenset({'admin', 'local_admin'})
MANAGER_ROLE = 'manager'


def _role_assignment_forbidden_response():
    return jsonify({'error': 'Только главный администратор может назначать администраторов'}), 403


def _can_assign_role(role):
    """local_admin может создавать только менеджеров; admin — любую роль."""
    if role in ADMIN_ROLES and session.get('role') != 'admin':
        return False
    if role not in ADMIN_ROLES | {MANAGER_ROLE}:
        return False
    return session.get('role') in ('admin', 'local_admin')


def _can_manage_user(target_role):
    """local_admin не может редактировать существующих администраторов."""
    if session.get('role') == 'admin':
        return True
    return target_role not in ADMIN_ROLES


def row_to_dict(cursor_description, row):
    if row is None:
        return None
    cols = [d[0] for d in cursor_description]
    return dict(zip(cols, row))


def rows_to_list(cursor_description, rows):
    cols = [d[0] for d in cursor_description]
    return [dict(zip(cols, r)) for r in rows]


EVENT_COLS = ['id', 'company_id', 'project_id', 'client_id', 'event_type', 'start_date', 'end_date',
              'responsible_user', 'description', 'status', 'result', 'completion_desc', 'rating']


def event_row(r):
    return dict(zip(EVENT_COLS, r))


# ================= АУТЕНТИФИКАЦИЯ =================
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or request.form
    username = data.get('username')
    password = data.get('password')
    conn = get_db_connection()
    user = conn.cursor().execute(
        "SELECT password, role, first_name, last_name, patronymic FROM users WHERE username = ?",
        (username,)).fetchone()
    conn.close()
    if user and check_password_hash(user[0], password):
        session['logged_in'] = True
        session['username'] = username
        session['role'] = user[1]
        session['first_name'] = user[2] or ''
        session['last_name'] = user[3] or ''
        session['patronymic'] = user[4] or ''
        return jsonify({'success': True, 'user': {
            'username': username, 'role': user[1], 'first_name': user[2], 'last_name': user[3]
        }})
    return jsonify({'error': 'Неверный логин или пароль!'}), 401


@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True})


@app.route('/api/me', methods=['GET'])
def me():
    if 'logged_in' not in session:
        return jsonify({'logged_in': False}), 200
    return jsonify({
        'logged_in': True,
        'username': session.get('username'),
        'role': session.get('role'),
        'first_name': session.get('first_name'),
        'last_name': session.get('last_name'),
        'patronymic': session.get('patronymic'),
    })


# ================= АДМИН ПАНЕЛЬ =================
@app.route('/api/admin/users', methods=['GET'])
@login_required
@admin_required
def admin_users():
    conn = get_db_connection()
    rows = conn.cursor().execute("SELECT id, username, role, first_name, last_name, email FROM users").fetchall()
    conn.close()
    cols = ['id', 'username', 'role', 'first_name', 'last_name', 'email']
    return jsonify([dict(zip(cols, r)) for r in rows])


@app.route('/api/admin/change_password', methods=['POST'])
@login_required
def admin_change_password():
    data = request.get_json(silent=True) or request.form
    new_pass = data.get('new_password', '')
    confirm = data.get('confirm_password', '')
    if new_pass != confirm or len(new_pass) < 4:
        return jsonify({'error': 'Ошибка смены пароля (пароли не совпадают или короче 4 символов)'}), 400
    conn = get_db_connection()
    conn.cursor().execute("UPDATE users SET password = ? WHERE username = ?",
                          (generate_password_hash(new_pass), session['username']))
    conn.commit(); conn.close()
    return jsonify({'success': True, 'message': 'Пароль изменен!'})


@app.route('/api/admin/users', methods=['POST'])
@login_required
@admin_required
def admin_create_user():
    data = request.get_json(silent=True) or request.form
    first_name = (data.get('first_name') or '').strip()
    last_name = (data.get('last_name') or '').strip()
    patronymic = (data.get('patronymic') or '').strip()
    email = (data.get('email') or '').strip()
    new_username = (data.get('username') or '').strip()
    new_password = (data.get('password') or '').strip()
    new_role = data.get('role', '')

    if not _can_assign_role(new_role):
        return _role_assignment_forbidden_response()

    if not first_name or not last_name or not email or not new_username or not new_password:
        return jsonify({'error': 'Заполните все обязательные поля!'}), 400

    conn = get_db_connection()
    if conn.cursor().execute("SELECT id FROM users WHERE username = ?", (new_username,)).fetchone():
        conn.close()
        return jsonify({'error': 'Логин уже занят!'}), 400

    conn.cursor().execute(
        '''INSERT INTO users (username, password, role, first_name, last_name, patronymic, email) VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (new_username, generate_password_hash(new_password), new_role, first_name, last_name, patronymic, email))
    conn.commit(); conn.close()
    return jsonify({'success': True, 'message': f'Пользователь {first_name} {last_name} успешно создан!'})


@app.route('/api/admin/users/<int:user_id>', methods=['GET'])
@login_required
@admin_required
def get_user(user_id):
    conn = get_db_connection()
    user = conn.cursor().execute(
        "SELECT id, username, role, first_name, last_name, patronymic, email FROM users WHERE id = ?",
        (user_id,)).fetchone()
    conn.close()
    if not user:
        return jsonify({'error': 'Не найден'}), 404
    cols = ['id', 'username', 'role', 'first_name', 'last_name', 'patronymic', 'email']
    return jsonify(dict(zip(cols, user)))


@app.route('/api/admin/users/<int:user_id>', methods=['PUT'])
@login_required
@admin_required
def edit_user(user_id):
    data = request.get_json(silent=True) or request.form
    first_name = (data.get('first_name') or '').strip()
    last_name = (data.get('last_name') or '').strip()
    patronymic = (data.get('patronymic') or '').strip()
    email = (data.get('email') or '').strip()
    new_username = (data.get('username') or '').strip()
    new_role = data.get('role', '')
    new_password = (data.get('password') or '').strip()

    conn = get_db_connection()
    cursor = conn.cursor()
    existing = cursor.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
    if not existing:
        conn.close()
        return jsonify({'error': 'Не найден'}), 404

    current_role = existing[0]
    if not _can_manage_user(current_role):
        conn.close()
        return _role_assignment_forbidden_response()
    if not _can_assign_role(new_role):
        conn.close()
        return _role_assignment_forbidden_response()

    if cursor.execute("SELECT id FROM users WHERE username = ? AND id != ?",
                      (new_username, user_id)).fetchone():
        conn.close()
        return jsonify({'error': 'Логин занят!'}), 400

    if new_password:
        conn.cursor().execute(
            '''UPDATE users SET username=?, role=?, password=?, first_name=?, last_name=?, patronymic=?, email=? WHERE id=?''',
            (new_username, new_role, generate_password_hash(new_password), first_name, last_name, patronymic,
             email, user_id))
    else:
        conn.cursor().execute(
            '''UPDATE users SET username=?, role=?, first_name=?, last_name=?, patronymic=?, email=? WHERE id=?''',
            (new_username, new_role, first_name, last_name, patronymic, email, user_id))
    conn.commit(); conn.close()
    return jsonify({'success': True, 'message': 'Пользователь обновлен!'})


@app.route('/api/admin/reports', methods=['GET'])
@login_required
@admin_required
def admin_reports_get():
    conn = get_db_connection()
    weekly_set = conn.cursor().execute(
        "SELECT recipient_ids, day_value, time_value FROM report_settings WHERE id = 1").fetchone()
    monthly_set = conn.cursor().execute(
        "SELECT recipient_ids, day_value, time_value FROM report_settings WHERE id = 2").fetchone()
    daily_set = conn.cursor().execute("SELECT recipient_ids, time_value FROM report_settings WHERE id = 3").fetchone()
    users = conn.cursor().execute(
        "SELECT id, first_name, last_name, email FROM users WHERE email IS NOT NULL AND email != ''").fetchall()
    conn.close()

    w_recipients = weekly_set[0].split(',') if weekly_set and weekly_set[0] else []
    m_recipients = monthly_set[0].split(',') if monthly_set and monthly_set[0] else []
    d_recipients = daily_set[0].split(',') if daily_set and daily_set[0] else []

    return jsonify({
        'users': [{'id': u[0], 'first_name': u[1], 'last_name': u[2], 'email': u[3]} for u in users],
        'weekly': {'recipients': w_recipients, 'day': weekly_set[1] if weekly_set else 0,
                   'time': weekly_set[2] if weekly_set else '13:00'},
        'monthly': {'recipients': m_recipients, 'day': monthly_set[1] if monthly_set else 1,
                    'time': monthly_set[2] if monthly_set else '13:00'},
        'daily': {'recipients': d_recipients, 'time': daily_set[1] if daily_set else '09:00'},
        'smtp_accounts': _smtp_accounts_status(),
        'scheduler_jobs': _scheduler_snapshot(),
    })


@app.route('/api/admin/reports/settings', methods=['POST'])
@login_required
@admin_required
def admin_reports_save():
    data = request.get_json(silent=True) or request.form
    report_type = (data.get('report_type') or '').strip()
    if report_type not in ('weekly', 'monthly', 'daily'):
        return jsonify({'error': 'Неверный тип отчета'}), 400

    recipients = data.getlist('recipients') if hasattr(data, 'getlist') else data.get('recipients', [])
    if isinstance(recipients, str):
        recipients = [recipients]
    recipients = _normalize_recipient_ids(recipients)
    recipient_str = ','.join(recipients) if recipients else ''
    time_value = (data.get('time_value') or '').strip()
    if not _is_valid_time_value(time_value):
        return jsonify({'error': 'Некорректное время. Формат HH:MM'}), 400

    conn = get_db_connection()
    if report_type == 'daily':
        conn.cursor().execute(
            '''INSERT OR REPLACE INTO report_settings (id, recipient_ids, frequency, day_value, time_value) VALUES (?, ?, 'daily', 0, ?)''',
            (3, recipient_str, time_value))
    else:
        db_id = 1 if report_type == 'weekly' else 2
        day_raw = data.get('day_value')
        try:
            day_value = int(day_raw)
        except (TypeError, ValueError):
            conn.close()
            return jsonify({'error': 'Некорректное значение дня'}), 400
        if report_type == 'weekly' and (day_value < 0 or day_value > 6):
            conn.close()
            return jsonify({'error': 'Для недельного отчета день должен быть от 0 до 6'}), 400
        if report_type == 'monthly' and (day_value < 1 or day_value > 28):
            conn.close()
            return jsonify({'error': 'Для месячного отчета день должен быть от 1 до 28'}), 400
        conn.cursor().execute(
            '''INSERT OR REPLACE INTO report_settings (id, recipient_ids, frequency, day_value, time_value) VALUES (?, ?, ?, ?, ?)''',
            (db_id, recipient_str, report_type, day_value, time_value))
    conn.commit(); conn.close()

    try:
        update_scheduler()
    except Exception as e:
        print(f"[SCHEDULER] Ошибка инициализации: {e}")

    return jsonify({'success': True, 'message': f'Настройки {"ежедневного " if report_type == "daily" else ""}отчета сохранены!'})


@app.route('/api/admin/smtp/passwords', methods=['POST'])
@login_required
@admin_required
def admin_smtp_passwords_save():
    data = request.get_json(silent=True) or request.form
    passwords = data.get('passwords', {})
    if not isinstance(passwords, dict):
        return jsonify({'error': 'Неверный формат паролей'}), 400

    for account in SMTP_ACCOUNTS:
        acc_id = account['id']
        if acc_id in passwords:
            SMTP_PASSWORDS[acc_id] = str(passwords.get(acc_id) or '').strip()

    configured = [a['email'] for a in SMTP_ACCOUNTS if SMTP_PASSWORDS.get(a['id'])]
    return jsonify({
        'success': True,
        'message': 'SMTP пароли обновлены в памяти текущего процесса.',
        'configured_accounts': configured,
    })


@app.route('/api/admin/smtp/check', methods=['POST'])
@login_required
@admin_required
def admin_smtp_check():
    checks = _smtp_check_accounts()
    any_ok = any(c['ok'] for c in checks)
    return jsonify({
        'success': any_ok,
        'checks': checks,
        'message': 'Проверка завершена',
    }), 200 if any_ok else 500


@app.route('/api/admin/self-check', methods=['GET'])
@login_required
@admin_required
def admin_self_check():
    checks = _smtp_check_accounts()
    any_smtp_ok = any(c['ok'] for c in checks)

    conn = get_db_connection()
    weekly = conn.cursor().execute("SELECT recipient_ids, day_value, time_value FROM report_settings WHERE id = 1").fetchone()
    monthly = conn.cursor().execute("SELECT recipient_ids, day_value, time_value FROM report_settings WHERE id = 2").fetchone()
    daily = conn.cursor().execute("SELECT recipient_ids, time_value FROM report_settings WHERE id = 3").fetchone()
    conn.close()

    report_state = {
        'weekly_configured': bool(weekly and weekly[0]),
        'monthly_configured': bool(monthly and monthly[0]),
        'daily_configured': bool(daily and daily[0]),
    }

    jobs = _scheduler_snapshot()
    ok = any_smtp_ok and any(report_state.values())
    return jsonify({
        'success': ok,
        'smtp': checks,
        'report_state': report_state,
        'scheduler_jobs': jobs,
    }), 200 if ok else 500


@app.route('/api/admin/reports/test/<kind>', methods=['POST'])
@login_required
def admin_reports_test(kind):
    if session.get('role') != 'admin':
        return jsonify({'error': 'Недостаточно прав'}), 403
    data = request.get_json(silent=True) or {}
    recipients = data.get('recipients')
    if isinstance(recipients, str):
        recipients = [recipients] if recipients else []
    elif recipients is None:
        recipients = None
    if kind == 'daily':
        ok = send_daily_plan_email(test_mode=True, recipient_ids_override=recipients)
        msg_ok = 'Тест ежедневного плана отправлен выбранным сотрудникам!'
        msg_fail = 'Не выбраны получатели, у них нет email или не настроены SMTP-пароли отправителей.'
    elif kind == 'weekly':
        ok = send_report_email('weekly', recipient_ids_override=recipients)
        msg_ok = 'Тест еженедельного отчета отправлен!'
        msg_fail = 'Не выбраны получатели, у них нет email или не настроены SMTP-пароли отправителей.'
    elif kind == 'monthly':
        ok = send_report_email('monthly', recipient_ids_override=recipients)
        msg_ok = 'Тест ежемесячного отчета отправлен!'
        msg_fail = 'Не выбраны получатели, у них нет email или не настроены SMTP-пароли отправителей.'
    else:
        return jsonify({'error': 'Неизвестный тип'}), 400
    if ok:
        return jsonify({'success': True, 'message': msg_ok})
    return jsonify({'error': msg_fail}), 500


@app.route('/api/admin/reports/demo/seed', methods=['POST'])
@login_required
@admin_required
def admin_reports_demo_seed():
    result = seed_demo_report_events()
    if not result.get('success'):
        return jsonify({'error': result.get('error', 'Ошибка')}), 400
    msg = (f"Создано {result['created']} тестовых мероприятий у {result['users']} пользователей "
           f"(удалено старых DEMO: {result['deleted']})")
    return jsonify({'success': True, 'message': msg, **result})


@app.route('/api/admin/reports/preview/<kind>', methods=['GET'])
@login_required
@admin_required
def admin_reports_preview(kind):
    if kind == 'weekly':
        html, _title = build_report_html('weekly')
        resp = make_response(html)
        resp.headers['Content-Type'] = 'text/html; charset=utf-8'
        return resp
    if kind == 'monthly':
        html, _title = build_report_html('monthly')
        resp = make_response(html)
        resp.headers['Content-Type'] = 'text/html; charset=utf-8'
        return resp
    if kind == 'daily':
        conn = get_db_connection()
        cursor = conn.cursor()
        users = cursor.execute(
            "SELECT username, first_name, last_name FROM users WHERE role != 'admin'"
        ).fetchall()
        if not users:
            users = cursor.execute("SELECT username, first_name, last_name FROM users").fetchall()
        sections = []
        for username, first_name, last_name in users:
            body, subject, full_name = build_daily_plan_html(
                cursor, username, first_name, last_name, test_mode=True)
            sections.append(
                f'<div style="margin-bottom:40px;border-bottom:2px solid #E2E8F0;padding-bottom:24px;">'
                f'<p style="color:#64748B;font-size:14px;">{subject}</p>{body}</div>'
            )
        conn.close()
        html = (
            '<!DOCTYPE html><html><head><meta charset="UTF-8">'
            '<title>Ежедневные планы (предпросмотр)</title></head>'
            '<body style="background:#F8FAFC;padding:20px;">'
            '<div style="max-width:700px;margin:0 auto;">'
            '<h2 style="color:#1E3A8A;">Ежедневные планы — предпросмотр</h2>'
            + ''.join(sections) + '</div></body></html>'
        )
        resp = make_response(html)
        resp.headers['Content-Type'] = 'text/html; charset=utf-8'
        return resp
    return jsonify({'error': 'Неизвестный тип'}), 400


@app.route('/api/admin/reports/demo/send/<kind>', methods=['POST'])
@login_required
def admin_reports_demo_send(kind):
    """Заполнить тестовыми мероприятиями и отправить отчёт на почту (только admin)."""
    if session.get('role') != 'admin':
        return jsonify({'error': 'Недостаточно прав'}), 403
    data = request.get_json(silent=True) or {}
    seed_first = data.get('seed', True)
    recipients = data.get('recipients')
    if isinstance(recipients, str):
        recipients = [recipients] if recipients else []
    if seed_first:
        seed_demo_report_events()
    if kind == 'daily':
        ok = send_daily_plan_email(test_mode=True, recipient_ids_override=recipients)
        msg_ok = 'Тестовые данные созданы. Ежедневный план отправлен на почту!'
        msg_fail = 'Данные созданы, но отправка не удалась: проверьте получателей, email и SMTP.'
    elif kind == 'weekly':
        ok = send_report_email('weekly', recipient_ids_override=recipients)
        msg_ok = 'Тестовые данные созданы. Еженедельный отчёт отправлен на почту!'
        msg_fail = 'Данные созданы, но отправка не удалась: проверьте получателей, email и SMTP.'
    elif kind == 'monthly':
        ok = send_report_email('monthly', recipient_ids_override=recipients)
        msg_ok = 'Тестовые данные созданы. Ежемесячный отчёт отправлен на почту!'
        msg_fail = 'Данные созданы, но отправка не удалась: проверьте получателей, email и SMTP.'
    else:
        return jsonify({'error': 'Неизвестный тип'}), 400
    if ok:
        return jsonify({'success': True, 'message': msg_ok})
    return jsonify({'error': msg_fail}), 500


# ================= ФИЗ. ЛИЦА =================
@app.route('/api/clients', methods=['GET'])
@login_required
def clients_physical():
    conn = get_db_connection()
    rows = conn.cursor().execute(
        "SELECT id, last_name, first_name, patronymic, phone, email, position FROM clients").fetchall()
    conn.close()
    cols = ['id', 'last_name', 'first_name', 'patronymic', 'phone', 'email', 'position']
    return jsonify([dict(zip(cols, r)) for r in rows])


@app.route('/api/clients', methods=['POST'])
@login_required
def add_client_physical():
    data = request.get_json(silent=True) or request.form
    company_id = request.args.get('company_id', type=int) or (data.get('company_id') and int(data.get('company_id')))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO clients (last_name, first_name, patronymic, dob, description, phone, email, position) 
                      VALUES (?,?,?,?,?,?,?,?)''',
                   (data.get('last_name', ''), data.get('first_name', ''), data.get('patronymic', ''),
                    data.get('dob', ''), data.get('description', ''), data.get('phone', ''),
                    data.get('email', ''), data.get('position', '')))
    client_id = cursor.lastrowid

    if company_id:
        cursor.execute("INSERT INTO company_employees (company_id, client_id, status) VALUES (?, ?, 'РАБОТАЕТ')",
                       (company_id, client_id))

    conn.commit(); conn.close()
    return jsonify({'success': True, 'id': client_id})


@app.route('/api/clients/<int:client_id>', methods=['GET'])
@login_required
def view_client_physical(client_id):
    conn = get_db_connection()
    client = conn.cursor().execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
    if not client:
        conn.close()
        return jsonify({'error': 'Не найден'}), 404

    client_cols = ['id', 'last_name', 'first_name', 'patronymic', 'dob', 'description', 'phone', 'email', 'position']

    employers = conn.cursor().execute(
        '''SELECT c.id, c.name, ce.status FROM company_employees ce JOIN companies c ON ce.company_id = c.id WHERE ce.client_id = ?''',
        (client_id,)).fetchall()

    client_events = conn.cursor().execute(
        '''SELECT id, event_type, start_date, end_date, responsible_user, description, status, result, completion_desc, rating FROM events WHERE client_id = ? ORDER BY start_date DESC''',
        (client_id,)).fetchall()
    conn.close()

    ev_cols = ['id', 'event_type', 'start_date', 'end_date', 'responsible_user', 'description', 'status', 'result',
               'completion_desc', 'rating']
    events_list = [dict(zip(ev_cols, e)) for e in client_events]

    return jsonify({
        'client': dict(zip(client_cols, client)),
        'employers': [{'id': e[0], 'name': e[1], 'status': e[2]} for e in employers],
        'planned_events': [e for e in events_list if e['status'] == 'planned'],
        'completed_events': [e for e in events_list if e['status'] == 'completed'],
        'cancelled_events': [e for e in events_list if e['status'] == 'cancelled'],
    })


@app.route('/api/clients/<int:client_id>', methods=['PUT'])
@login_required
def edit_client_physical(client_id):
    data = request.get_json(silent=True) or request.form
    conn = get_db_connection()
    conn.cursor().execute(
        '''UPDATE clients SET last_name=?, first_name=?, patronymic=?, dob=?, description=?, phone=?, email=?, position=? WHERE id=?''',
        (data.get('last_name', ''), data.get('first_name', ''), data.get('patronymic', ''),
         data.get('dob', ''), data.get('description', ''), data.get('phone', ''),
         data.get('email', ''), data.get('position', ''), client_id))
    conn.commit(); conn.close()
    return jsonify({'success': True, 'message': 'Данные обновлены!'})


@app.route('/api/clients/<int:client_id>/available_employers', methods=['GET'])
@login_required
def client_available_employers(client_id):
    conn = get_db_connection()
    rows = conn.cursor().execute(
        '''SELECT id, name, type, activity, country FROM companies
           WHERE id NOT IN (
             SELECT company_id FROM company_employees WHERE client_id = ? AND status = 'РАБОТАЕТ'
           ) ORDER BY name''',
        (client_id,)).fetchall()
    conn.close()
    cols = ['id', 'name', 'type', 'activity', 'country']
    return jsonify([dict(zip(cols, r)) for r in rows])


@app.route('/api/clients/<int:client_id>/employers/<int:company_id>', methods=['DELETE'])
@login_required
def client_unlink_employer(client_id, company_id):
    return unlink_employee(company_id, client_id)


# Мероприятия Физ. лица
@app.route('/api/clients/<int:client_id>/events', methods=['POST'])
@login_required
def add_client_event(client_id):
    data = request.get_json(silent=True) or request.form
    responsible_user = session['username'] if session['role'] == 'manager' else data.get('responsible_user',
                                                                                          session['username'])
    planned_date = data.get('planned_date', '')

    conn = get_db_connection()
    conn.cursor().execute('''INSERT INTO events (client_id, company_id, project_id, event_type, start_date, end_date, responsible_user, description, status) 
                             VALUES (?, NULL, NULL, ?, ?, NULL, ?, ?, 'planned')''',
                          (client_id, data.get('event_type', ''), planned_date, responsible_user,
                           data.get('description', '')))
    conn.commit(); conn.close()
    return jsonify({'success': True, 'message': 'Мероприятие создано!'})


@app.route('/api/clients/<int:client_id>/events/<int:event_id>/complete', methods=['POST'])
@login_required
def complete_client_event(client_id, event_id):
    conn = get_db_connection()
    conn.cursor().execute("UPDATE events SET status = 'completed' WHERE id = ?", (event_id,))
    conn.commit(); conn.close()
    return jsonify({'success': True})


@app.route('/api/clients/<int:client_id>/events/<int:event_id>/cancel', methods=['POST'])
@login_required
def cancel_client_event(client_id, event_id):
    conn = get_db_connection()
    conn.cursor().execute("UPDATE events SET status = 'cancelled' WHERE id = ?", (event_id,))
    conn.commit(); conn.close()
    return jsonify({'success': True})


@app.route('/api/clients/<int:client_id>/events/<int:event_id>', methods=['GET'])
@login_required
def view_client_event(client_id, event_id):
    conn = get_db_connection()
    event = conn.cursor().execute("SELECT * FROM events WHERE id = ? AND client_id = ?",
                                  (event_id, client_id)).fetchone()
    conn.close()
    if not event:
        return jsonify({'error': 'Не найдено'}), 404
    return jsonify(event_row(event))


@app.route('/api/clients/<int:client_id>/events/<int:event_id>/finish', methods=['POST'])
@login_required
def edit_client_event(client_id, event_id):
    data = request.get_json(silent=True) or request.form
    err = _validate_finish_payload(data)
    if err:
        return jsonify({'error': err}), 400
    conn = get_db_connection()
    event = conn.cursor().execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    if not event:
        conn.close()
        return jsonify({'error': 'Не найдено'}), 404
    conn.cursor().execute(
        '''UPDATE events SET status='completed', result=?, completion_desc=?, rating=? WHERE id=?''',
        (data.get('result', ''), data.get('completion_desc', ''), data.get('rating', 0), event_id))
    conn.commit(); conn.close()
    return jsonify({'success': True, 'message': 'Мероприятие завершено!'})


# ================= КОМПАНИИ =================
@app.route('/api/companies', methods=['GET'])
@login_required
def clients_companies():
    conn = get_db_connection()
    rows = conn.cursor().execute(
        '''SELECT c.id, c.name, c.type, c.activity, c.website, c.country, COUNT(ce.client_id) as emp_count FROM companies c LEFT JOIN company_employees ce ON c.id = ce.company_id GROUP BY c.id''').fetchall()
    conn.close()
    cols = ['id', 'name', 'type', 'activity', 'website', 'country', 'emp_count']
    return jsonify([dict(zip(cols, r)) for r in rows])


@app.route('/api/companies', methods=['POST'])
@login_required
def add_company():
    data = request.get_json(silent=True) or request.form
    err, website = _validate_company_payload(data)
    if err:
        return jsonify({'error': err}), 400
    project_id = request.args.get('project_id', type=int) or (data.get('project_id') and int(data.get('project_id')))
    client_id = request.args.get('client_id', type=int) or (data.get('client_id') and int(data.get('client_id')))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO companies (name, country, activity, type, website, description) 
                      VALUES (?, ?, ?, ?, ?, ?)''',
                   (data.get('name', ''), data.get('country', ''), data.get('activity', ''), data.get('type', ''),
                    website, data.get('description', '')))
    company_id = cursor.lastrowid

    if project_id:
        cursor.execute("INSERT INTO project_companies (project_id, company_id) VALUES (?, ?)",
                       (project_id, company_id))
    if client_id:
        try:
            cursor.execute(
                "INSERT INTO company_employees (company_id, client_id, status) VALUES (?,?, 'РАБОТАЕТ')",
                (company_id, client_id))
        except sqlite3.IntegrityError:
            cursor.execute(
                "UPDATE company_employees SET status = 'РАБОТАЕТ' WHERE company_id = ? AND client_id = ?",
                (company_id, client_id))

    conn.commit(); conn.close()
    return jsonify({'success': True, 'id': company_id})


@app.route('/api/companies/<int:company_id>', methods=['GET'])
@login_required
def view_company(company_id):
    conn = get_db_connection()
    comp = conn.cursor().execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
    if not comp:
        conn.close()
        return jsonify({'error': 'Не найдена'}), 404
    comp_cols = ['id', 'name', 'country', 'activity', 'type', 'website', 'description']

    employees = conn.cursor().execute(
        '''SELECT cl.id, cl.last_name, cl.first_name, cl.patronymic, cl.position FROM clients cl JOIN company_employees ce ON cl.id = ce.client_id WHERE ce.company_id = ? AND ce.status = 'РАБОТАЕТ' ''',
        (company_id,)).fetchall()
    projects = conn.cursor().execute(
        '''SELECT p.id, p.name, p.status, p.address FROM projects p JOIN project_companies pc ON p.id = pc.project_id WHERE pc.company_id = ?''',
        (company_id,)).fetchall()
    events = conn.cursor().execute(
        '''SELECT id, event_type, start_date, end_date, responsible_user, description, status, result, completion_desc, rating FROM events WHERE company_id = ? ORDER BY start_date DESC''',
        (company_id,)).fetchall()
    conn.close()

    ev_cols = ['id', 'event_type', 'start_date', 'end_date', 'responsible_user', 'description', 'status', 'result',
               'completion_desc', 'rating']
    events_list = [dict(zip(ev_cols, e)) for e in events]

    return jsonify({
        'company': dict(zip(comp_cols, comp)),
        'employees': [{'id': e[0], 'last_name': e[1], 'first_name': e[2], 'patronymic': e[3], 'position': e[4]} for e
                      in employees],
        'projects': [{'id': p[0], 'name': p[1], 'status': p[2], 'address': p[3]} for p in projects],
        'planned_events': [e for e in events_list if e['status'] == 'planned'],
        'completed_events': [e for e in events_list if e['status'] == 'completed'],
        'cancelled_events': [e for e in events_list if e['status'] == 'cancelled'],
    })


@app.route('/api/companies/<int:company_id>', methods=['PUT'])
@login_required
def edit_company(company_id):
    data = request.get_json(silent=True) or request.form
    err, website = _validate_company_payload(data)
    if err:
        return jsonify({'error': err}), 400
    conn = get_db_connection()
    conn.cursor().execute(
        '''UPDATE companies SET name=?, country=?, activity=?, type=?, website=?, description=? WHERE id=?''',
        (data.get('name', ''), data.get('country', ''), data.get('activity', ''),
         data.get('type', ''), website, data.get('description', ''), company_id))
    conn.commit(); conn.close()
    return jsonify({'success': True, 'message': 'Компания обновлена!'})


# Мероприятия Компании
@app.route('/api/companies/<int:company_id>/events', methods=['POST'])
@login_required
def add_event(company_id):
    data = request.get_json(silent=True) or request.form
    responsible_user = session['username'] if session['role'] == 'manager' else data.get('responsible_user',
                                                                                          session['username'])
    planned_date = data.get('planned_date', '')

    conn = get_db_connection()
    conn.cursor().execute('''INSERT INTO events (company_id, project_id, client_id, event_type, start_date, end_date, responsible_user, description, status) 
                             VALUES (?, NULL, NULL, ?, ?, NULL, ?, ?, 'planned')''',
                          (company_id, data.get('event_type', ''), planned_date, responsible_user,
                           data.get('description', '')))
    conn.commit(); conn.close()
    return jsonify({'success': True, 'message': 'Мероприятие создано!'})


@app.route('/api/companies/<int:company_id>/events/<int:event_id>/complete', methods=['POST'])
@login_required
def complete_event(company_id, event_id):
    conn = get_db_connection()
    conn.cursor().execute("UPDATE events SET status = 'completed' WHERE id = ?", (event_id,))
    conn.commit(); conn.close()
    return jsonify({'success': True})


@app.route('/api/companies/<int:company_id>/events/<int:event_id>/cancel', methods=['POST'])
@login_required
def cancel_event(company_id, event_id):
    conn = get_db_connection()
    conn.cursor().execute("UPDATE events SET status = 'cancelled' WHERE id = ?", (event_id,))
    conn.commit(); conn.close()
    return jsonify({'success': True})


@app.route('/api/companies/<int:company_id>/events/<int:event_id>', methods=['GET'])
@login_required
def view_event(company_id, event_id):
    conn = get_db_connection()
    event = conn.cursor().execute("SELECT * FROM events WHERE id = ? AND company_id = ?",
                                  (event_id, company_id)).fetchone()
    conn.close()
    if not event:
        return jsonify({'error': 'Не найдено'}), 404
    return jsonify(event_row(event))


@app.route('/api/companies/<int:company_id>/events/<int:event_id>/finish', methods=['POST'])
@login_required
def edit_event(company_id, event_id):
    data = request.get_json(silent=True) or request.form
    err = _validate_finish_payload(data)
    if err:
        return jsonify({'error': err}), 400
    conn = get_db_connection()
    event = conn.cursor().execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    if not event:
        conn.close()
        return jsonify({'error': 'Не найдено'}), 404
    conn.cursor().execute(
        '''UPDATE events SET status='completed', result=?, completion_desc=?, rating=? WHERE id=?''',
        (data.get('result', ''), data.get('completion_desc', ''), data.get('rating', 0), event_id))
    conn.commit(); conn.close()
    return jsonify({'success': True, 'message': 'Мероприятие завершено!'})


@app.route('/api/companies/<int:company_id>/available_employees', methods=['GET'])
@login_required
def select_employee(company_id):
    conn = get_db_connection()
    rows = conn.cursor().execute(
        '''SELECT id, last_name, first_name, patronymic, position FROM clients WHERE id NOT IN (SELECT client_id FROM company_employees WHERE company_id = ? AND status = 'РАБОТАЕТ')''',
        (company_id,)).fetchall()
    conn.close()
    cols = ['id', 'last_name', 'first_name', 'patronymic', 'position']
    return jsonify([dict(zip(cols, r)) for r in rows])


@app.route('/api/companies/<int:company_id>/employees', methods=['POST'])
@login_required
def link_employee(company_id):
    data = request.get_json(silent=True) or request.form
    client_id = data.get('client_id')
    if not client_id:
        return jsonify({'error': 'client_id обязателен'}), 400
    conn = get_db_connection()
    try:
        conn.cursor().execute(
            "INSERT INTO company_employees (company_id, client_id, status) VALUES (?,?, 'РАБОТАЕТ')",
            (company_id, client_id))
        conn.commit()
        message = 'Сотрудник добавлен!'
    except sqlite3.IntegrityError:
        conn.cursor().execute(
            "UPDATE company_employees SET status = 'РАБОТАЕТ' WHERE company_id = ? AND client_id = ?",
            (company_id, client_id))
        conn.commit()
        message = 'Сотрудник возвращен!'
    conn.close()
    return jsonify({'success': True, 'message': message})


@app.route('/api/companies/<int:company_id>/employees/<int:client_id>', methods=['DELETE'])
@login_required
def unlink_employee(company_id, client_id):
    conn = get_db_connection()
    conn.cursor().execute("UPDATE company_employees SET status = 'РАБОТАЛ' WHERE company_id = ? AND client_id = ?",
                          (company_id, client_id))
    conn.commit(); conn.close()
    return jsonify({'success': True, 'message': 'Сотрудник удален (статус: РАБОТАЛ)'})


# ================= ПРОЕКТЫ =================
@app.route('/api/projects', methods=['GET'])
@login_required
def clients_projects():
    conn = get_db_connection()
    rows = conn.cursor().execute(
        '''SELECT p.id, p.name, p.project_type, p.status, p.address, p.region, p.budget, p.currency,
                  COUNT(pc.company_id) as comp_count FROM projects p
           LEFT JOIN project_companies pc ON p.id = pc.project_id GROUP BY p.id''').fetchall()
    conn.close()
    cols = ['id', 'name', 'project_type', 'status', 'address', 'region', 'budget', 'currency', 'comp_count']
    return jsonify([dict(zip(cols, r)) for r in rows])


@app.route('/api/projects', methods=['POST'])
@login_required
def add_project():
    data = request.get_json(silent=True) or request.form
    err = _validate_project_payload(data)
    if err:
        return jsonify({'error': err}), 400
    currency = (data.get('currency') or 'RUB').strip() or 'RUB'
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        '''INSERT INTO projects (name, project_type, status, end_date, area, address, region, budget, cp_amount, currency)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (data.get('name', ''), data.get('project_type', ''), data.get('status', ''),
         data.get('end_date', ''), data.get('area', ''), data.get('address', '').strip(),
         data.get('region', '').strip(), data.get('budget', ''), data.get('cp_amount', ''), currency))
    project_id = cursor.lastrowid
    conn.commit(); conn.close()
    return jsonify({'success': True, 'id': project_id})


@app.route('/api/projects/<int:project_id>', methods=['GET'])
@login_required
def view_project(project_id):
    conn = get_db_connection()
    proj = conn.cursor().execute(
        '''SELECT id, name, project_type, status, end_date, area, address, region, budget, cp_amount, currency
           FROM projects WHERE id = ?''',
        (project_id,)).fetchone()
    if not proj:
        conn.close()
        return jsonify({'error': 'Не найден'}), 404
    proj_cols = ['id', 'name', 'project_type', 'status', 'end_date', 'area', 'address', 'region', 'budget', 'cp_amount', 'currency']

    companies = conn.cursor().execute(
        '''SELECT c.id, c.name, c.type FROM companies c JOIN project_companies pc ON c.id = pc.company_id WHERE pc.project_id = ?''',
        (project_id,)).fetchall()
    events = conn.cursor().execute(
        '''SELECT id, event_type, start_date, end_date, responsible_user, description, status, result, completion_desc, rating FROM events WHERE project_id = ? ORDER BY start_date DESC''',
        (project_id,)).fetchall()
    conn.close()

    ev_cols = ['id', 'event_type', 'start_date', 'end_date', 'responsible_user', 'description', 'status', 'result',
               'completion_desc', 'rating']
    events_list = [dict(zip(ev_cols, e)) for e in events]

    return jsonify({
        'project': dict(zip(proj_cols, proj)),
        'companies': [{'id': c[0], 'name': c[1], 'type': c[2]} for c in companies],
        'planned_events': [e for e in events_list if e['status'] == 'planned'],
        'completed_events': [e for e in events_list if e['status'] == 'completed'],
        'cancelled_events': [e for e in events_list if e['status'] == 'cancelled'],
    })


@app.route('/api/projects/<int:project_id>', methods=['PUT'])
@login_required
def edit_project(project_id):
    data = request.get_json(silent=True) or request.form
    err = _validate_project_payload(data)
    if err:
        return jsonify({'error': err}), 400
    currency = (data.get('currency') or 'RUB').strip() or 'RUB'
    conn = get_db_connection()
    conn.cursor().execute(
        '''UPDATE projects SET name=?, project_type=?, status=?, end_date=?, area=?, address=?, region=?,
           budget=?, cp_amount=?, currency=? WHERE id=?''',
        (data.get('name', ''), data.get('project_type', ''), data.get('status', ''),
         data.get('end_date', ''), data.get('area', ''), data.get('address', '').strip(),
         data.get('region', '').strip(), data.get('budget', ''), data.get('cp_amount', ''), currency, project_id))
    conn.commit(); conn.close()
    return jsonify({'success': True, 'message': 'Проект обновлен!'})


# Мероприятия Проекта
@app.route('/api/projects/<int:project_id>/events', methods=['POST'])
@login_required
def add_project_event(project_id):
    data = request.get_json(silent=True) or request.form
    responsible_user = session['username'] if session['role'] == 'manager' else data.get('responsible_user',
                                                                                          session['username'])
    planned_date = data.get('planned_date', '')

    conn = get_db_connection()
    conn.cursor().execute('''INSERT INTO events (project_id, company_id, client_id, event_type, start_date, end_date, responsible_user, description, status) 
                             VALUES (?, NULL, NULL, ?, ?, NULL, ?, ?, 'planned')''',
                          (project_id, data.get('event_type', ''), planned_date, responsible_user,
                           data.get('description', '')))
    conn.commit(); conn.close()
    return jsonify({'success': True, 'message': 'Мероприятие создано!'})


@app.route('/api/projects/<int:project_id>/events/<int:event_id>/complete', methods=['POST'])
@login_required
def complete_project_event(project_id, event_id):
    conn = get_db_connection()
    conn.cursor().execute("UPDATE events SET status = 'completed' WHERE id = ?", (event_id,))
    conn.commit(); conn.close()
    return jsonify({'success': True})


@app.route('/api/projects/<int:project_id>/events/<int:event_id>/cancel', methods=['POST'])
@login_required
def cancel_project_event(project_id, event_id):
    conn = get_db_connection()
    conn.cursor().execute("UPDATE events SET status = 'cancelled' WHERE id = ?", (event_id,))
    conn.commit(); conn.close()
    return jsonify({'success': True})


@app.route('/api/projects/<int:project_id>/events/<int:event_id>', methods=['GET'])
@login_required
def view_project_event(project_id, event_id):
    conn = get_db_connection()
    event = conn.cursor().execute("SELECT * FROM events WHERE id = ? AND project_id = ?",
                                  (event_id, project_id)).fetchone()
    conn.close()
    if not event:
        return jsonify({'error': 'Не найдено'}), 404
    return jsonify(event_row(event))


@app.route('/api/projects/<int:project_id>/events/<int:event_id>/finish', methods=['POST'])
@login_required
def edit_project_event(project_id, event_id):
    data = request.get_json(silent=True) or request.form
    err = _validate_finish_payload(data)
    if err:
        return jsonify({'error': err}), 400
    conn = get_db_connection()
    event = conn.cursor().execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    if not event:
        conn.close()
        return jsonify({'error': 'Не найдено'}), 404
    conn.cursor().execute(
        '''UPDATE events SET status='completed', result=?, completion_desc=?, rating=? WHERE id=?''',
        (data.get('result', ''), data.get('completion_desc', ''), data.get('rating', 0), event_id))
    conn.commit(); conn.close()
    return jsonify({'success': True, 'message': 'Мероприятие завершено!'})


@app.route('/api/projects/<int:project_id>/available_companies', methods=['GET'])
@login_required
def select_company_for_project(project_id):
    conn = get_db_connection()
    rows = conn.cursor().execute(
        '''SELECT id, name, type FROM companies WHERE id NOT IN (SELECT company_id FROM project_companies WHERE project_id = ?)''',
        (project_id,)).fetchall()
    conn.close()
    cols = ['id', 'name', 'type']
    return jsonify([dict(zip(cols, r)) for r in rows])


@app.route('/api/projects/<int:project_id>/companies', methods=['POST'])
@login_required
def link_company_to_project(project_id):
    data = request.get_json(silent=True) or request.form
    company_id = data.get('company_id')
    if not company_id:
        return jsonify({'error': 'company_id обязателен'}), 400
    conn = get_db_connection()
    try:
        conn.cursor().execute("INSERT INTO project_companies (project_id, company_id) VALUES (?,?)",
                              (project_id, company_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Компания добавлена в проект!'})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Компания уже в проекте.'}), 400


@app.route('/api/projects/<int:project_id>/companies/<int:company_id>', methods=['DELETE'])
@login_required
def unlink_company_from_project(project_id, company_id):
    conn = get_db_connection()
    conn.cursor().execute("DELETE FROM project_companies WHERE project_id = ? AND company_id = ?",
                          (project_id, company_id))
    conn.commit(); conn.close()
    return jsonify({'success': True, 'message': 'Компания удалена из проекта'})


# ================= СПИСОК ПОЛЬЗОВАТЕЛЕЙ (для select'ов) =================
@app.route('/api/users', methods=['GET'])
@login_required
def users_list():
    conn = get_db_connection()
    rows = conn.cursor().execute("SELECT username FROM users").fetchall()
    conn.close()
    return jsonify([r[0] for r in rows])


@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
