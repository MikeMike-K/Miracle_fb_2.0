#!/usr/bin/env python3
"""
Предпросмотр отчётов Miracle без отправки почты.

Примеры:
  python preview_reports.py seed
  python preview_reports.py weekly --open
  python preview_reports.py monthly
  python preview_reports.py daily
  python preview_reports.py daily --user admin
  python preview_reports.py all --open
"""
import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import (  # noqa: E402
    build_report_html,
    build_daily_plan_html,
    get_db_connection,
    seed_demo_report_events,
)

OUTPUT_DIR = Path(__file__).resolve().parent / 'report_previews'


def _safe_filename(name: str) -> str:
    return re.sub(r'[^\w\-.]+', '_', name, flags=re.UNICODE)


def seed_demo_events():
    result = seed_demo_report_events()
    if not result.get('success'):
        print(f"ОШИБКА: {result.get('error', 'неизвестная ошибка')}")
        return 1
    print(f"Готово: удалено старых DEMO: {result['deleted']}, создано: {result['created']}, "
          f"пользователей: {result['users']}")
    if result.get('company'):
        print(f"Привязка к компании: {result['company']}")
    elif result.get('project'):
        print(f"Привязка к проекту: {result['project']}")
    return 0


def save_html(path: Path, html: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding='utf-8')
    print(f'  -> {path}')


def preview_weekly(open_file: bool):
    html, title = build_report_html('weekly')
    path = OUTPUT_DIR / 'weekly_report.html'
    save_html(path, html)
    if open_file:
        os.startfile(path)
    print(f'Отчёт: {title}')
    return 0


def preview_monthly(open_file: bool):
    html, title = build_report_html('monthly')
    path = OUTPUT_DIR / 'monthly_report.html'
    save_html(path, html)
    if open_file:
        os.startfile(path)
    print(f'Отчёт: {title}')
    return 0


def preview_daily(username: str | None, open_file: bool):
    conn = get_db_connection()
    cursor = conn.cursor()

    if username:
        users = cursor.execute(
            "SELECT username, first_name, last_name FROM users WHERE username = ?", (username,)
        ).fetchall()
        if not users:
            conn.close()
            print(f'ОШИБКА: пользователь "{username}" не найден')
            return 1
    else:
        users = cursor.execute(
            "SELECT username, first_name, last_name FROM users WHERE role != 'admin'"
        ).fetchall()
        if not users:
            users = cursor.execute("SELECT username, first_name, last_name FROM users").fetchall()

    for uname, first_name, last_name in users:
        html, subject, full_name = build_daily_plan_html(
            cursor, uname, first_name, last_name, test_mode=True)
        fname = _safe_filename(f'daily_{uname}.html')
        path = OUTPUT_DIR / fname
        save_html(path, html)
        print(f'  {full_name}: {subject}')
        if open_file and len(users) == 1:
            os.startfile(path)

    conn.close()
    if open_file and len(users) > 1:
        os.startfile(OUTPUT_DIR)
    return 0


def main():
    parser = argparse.ArgumentParser(description='Предпросмотр отчётов Miracle (без SMTP)')
    parser.add_argument(
        'action',
        choices=['seed', 'weekly', 'monthly', 'daily', 'all'],
        help='seed — тестовые мероприятия; weekly/monthly/daily — HTML; all — всё сразу',
    )
    parser.add_argument('--user', help='Логин для daily (иначе все не-админы)')
    parser.add_argument('--open', action='store_true', help='Открыть HTML в браузере (Windows)')
    args = parser.parse_args()

    if args.action == 'seed':
        return seed_demo_events()
    if args.action == 'weekly':
        return preview_weekly(args.open)
    if args.action == 'monthly':
        return preview_monthly(args.open)
    if args.action == 'daily':
        return preview_daily(args.user, args.open)

    seed_demo_events()
    preview_weekly(False)
    preview_monthly(False)
    preview_daily(args.user, args.open)
    print(f'\nВсе превью в папке: {OUTPUT_DIR}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
