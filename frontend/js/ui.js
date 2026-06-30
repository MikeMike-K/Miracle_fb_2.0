/** Общие UI-хелперы Miracle: логотип, bootstrap bundle, шапки страниц. */

const MIRACLE_LOGO_SRC = '../assets/logo.svg';

function miracleLogoHtml({ size = 36, className = '' } = {}) {
  return `<img src="${MIRACLE_LOGO_SRC}" alt="" width="${size}" height="${size}" class="miracle-logo-img ${className}" aria-hidden="true">`;
}

function miracleBrandBlockHtml({ subtitle = 'CRM', compact = false } = {}) {
  const sub = compact
    ? `<span class="miracle-brand-sub">${escapeHtml(subtitle)}</span>`
    : `<span class="miracle-brand-sub d-block">Miracle <strong>2.0</strong> · ${escapeHtml(subtitle)}</span>`;
  return `
    <span class="miracle-brand ${compact ? 'miracle-brand--compact' : ''}">
      ${miracleLogoHtml({ size: compact ? 32 : 40 })}
      <span class="miracle-brand-text">
        <span class="miracle-brand-title">Miracle</span>
        ${sub}
      </span>
    </span>`;
}

function ensureBootstrapBundle() {
  if (window.bootstrap || document.getElementById('bootstrap-bundle')) return;
  const s = document.createElement('script');
  s.id = 'bootstrap-bundle';
  s.src = 'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js';
  document.body.appendChild(s);
}

function ensureMiracleFonts() {
  if (document.getElementById('miracle-fonts')) return;
  const link = document.createElement('link');
  link.id = 'miracle-fonts';
  link.rel = 'stylesheet';
  link.href = 'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap';
  document.head.appendChild(link);
}

function initMiracleUi() {
  ensureMiracleFonts();
  ensureBootstrapBundle();
  document.body.classList.add('miracle-app');
}

function pageHeaderHtml(title, actionsHtml = '') {
  return `
    <div class="page-header">
      <div class="page-header__main">
        <h1 class="page-title">${escapeHtml(title)}</h1>
      </div>
      ${actionsHtml ? `<div class="page-header__actions">${actionsHtml}</div>` : ''}
    </div>`;
}
