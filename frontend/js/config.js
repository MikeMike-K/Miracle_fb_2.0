// Продакшен (GitHub Pages): укажите URL backend на Railway/Render.
// Или задайте переменную репозитория API_BASE_URL — тогда config подставится при деплое.
const PRODUCTION_API = 'https://miraclefb20-production.up.railway.app';

if (location.hostname.endsWith('github.io')) {
  window.API_BASE = window.API_BASE || PRODUCTION_API;
} else {
  // Локально: backend на порту 5000 того же хоста, что и страница.
  window.API_BASE = window.API_BASE || `${location.protocol}//${location.hostname}:5000`;
}
