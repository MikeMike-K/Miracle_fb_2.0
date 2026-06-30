# Miracle_2.0 — backend / frontend

Проект разделён на два независимых модуля:

```
backend/    — Flask REST API (JSON), вся бизнес-логика и работа с БД
frontend/   — статичный сайт (HTML/CSS/JS), обращается к backend через fetch()
```

## backend

Полностью отвечает за данные: пользователи, физ. лица, компании, проекты,
мероприятия, авторизация (по cookie-сессии) и автоматическая рассылка отчётов.
Все маршруты теперь отдают JSON и находятся под префиксом `/api/...`
(например `POST /api/login`, `GET /api/companies`, `POST /api/projects/<id>/events`).

Запуск локально:
```
cd backend
pip install -r requirements.txt
python app.py        # стартует на http://localhost:5000
```

Используется та же база данных (`database.db` — SQLite локально,
PostgreSQL автоматически на Railway через `DATABASE_URL`), та же схема
таблиц и та же логика рассылки писем/планировщика, что и в исходном
приложении — изменился только способ отдачи данных (JSON вместо HTML).

По умолчанию разрешены кросс-доменные запросы с cookie (CORS,
`supports_credentials=True`). Для продакшена задайте переменную окружения
`FRONTEND_ORIGIN` (адрес фронтенда) и `SESSION_COOKIE_SECURE=1` при работе
по HTTPS.

## frontend

Набор статичных HTML-страниц с минимальным vanilla JS, который через
`fetch()` (см. `frontend/js/api.js`) обращается к backend API и сам
отрисовывает интерфейс. Никакого сервера для frontend не требуется — это
просто статика, которую можно открыть напрямую или раздать любым
веб-сервером (nginx, Netlify, GitHub Pages и т.д.).

Перед запуском укажите адрес backend в `frontend/js/config.js`:
```js
window.API_BASE = 'http://localhost:5000'; // или адрес вашего backend на проде
```

Запуск локально (любой статик-сервер, например):
```
cd frontend
python3 -m http.server 8080
# откройте http://localhost:8080
```

Структура страниц (`frontend/pages/`):
- `login.html` — вход
- `main.html` — главная
- `clients_physical.html`, `client_form.html` — физ. лица (список / карточка+мероприятия)
- `companies_list.html`, `company_form.html` — компании (список / карточка+сотрудники+проекты+мероприятия)
- `projects_list.html`, `project_form.html` — проекты (список / карточка+компании+мероприятия)
- `view_event.html`, `edit_event.html` — просмотр и завершение мероприятия (универсальные, параметр `ctx=client|company|project`)
- `select_employee.html`, `select_company_for_project.html` — привязка сущностей
- `admin.html`, `admin_edit_user.html`, `admin_reports.html` — администрирование и настройки автоматических отчётов

## Что важно знать при деплое

- backend и frontend теперь можно деплоить отдельно (разные хостинги/домены).
- Авторизация — через cookie сессии Flask; frontend всегда шлёт запросы с
  `credentials: 'include'`, поэтому backend и frontend должны быть на HTTPS
  и с корректно настроенным CORS, если находятся на разных доменах.
- SMTP-логика рассылки отчётов (явки/пароли в коде) перенесена как есть —
  рекомендуется вынести `SMTP_EMAIL` / `SMTP_PASSWORD` / `SECRET_KEY` в
  переменные окружения перед публичным деплоем.
