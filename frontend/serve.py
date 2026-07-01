"""Локальный сервер frontend с понятными ссылками при запуске."""
import os
import socket
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_PORT = int(os.environ.get("FRONTEND_PORT", "8081"))
MAX_TRIES = 20


def find_free_port(start: int) -> int:
    for port in range(start, start + MAX_TRIES):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise SystemExit(
        f"Не удалось найти свободный порт в диапазоне {start}–{start + MAX_TRIES - 1}"
    )


def print_banner(port: int, requested: int) -> None:
    base = f"http://localhost:{port}"
    login = f"{base}/pages/login.html"

    lines = [
        "",
        "=" * 62,
        "  Miracle 2.0 — frontend запущен",
        "=" * 62,
    ]
    if port != requested:
        lines.extend([f"  Порт {requested} занят → используется порт {port}", ""])
    lines.extend([
        "  Откройте в браузере (скопируйте ссылку):",
        f"    {base}",
        f"    {login}",
        "",
        "  Логин по умолчанию: admin / admin123",
        "",
        "  Backend API (запустите отдельно в папке backend):",
        "    http://localhost:5000/api/health",
        "",
        "  Остановка: Ctrl+C",
        "=" * 62,
        "",
    ])
    for line in lines:
        print(line, flush=True)


def main() -> None:
    root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(root)

    port = find_free_port(DEFAULT_PORT)
    print_banner(port, DEFAULT_PORT)

    with ThreadingHTTPServer(("127.0.0.1", port), SimpleHTTPRequestHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nСервер остановлен.")


if __name__ == "__main__":
    main()
