function renderNavbar(active = '', me = null) {
  const el = document.getElementById('navbar');
  if (!el) return;

  if (typeof initMiracleUi === 'function') initMiracleUi();

  const showAdmin = me && ['admin', 'local_admin'].includes(me.role);
  const userName = me
    ? [me.first_name, me.patronymic].filter(Boolean).join(' ') || me.username
    : '';

  const brandHtml = typeof miracleBrandBlockHtml === 'function'
    ? miracleBrandBlockHtml({ subtitle: 'CRM', compact: true })
    : '<span class="miracle-brand-title">Miracle</span>';

  el.innerHTML = `
  <nav class="navbar navbar-expand-lg navbar-dark navbar-custom sticky-top">
    <div class="container">
      <a class="navbar-brand" href="main.html">${brandHtml}</a>
      <button class="navbar-toggler border-0" type="button" data-bs-toggle="collapse" data-bs-target="#navMenu" aria-label="Меню">
        <span class="navbar-toggler-icon"></span>
      </button>
      <div class="collapse navbar-collapse" id="navMenu">
        <ul class="navbar-nav me-auto ms-lg-3">
          <li class="nav-item"><a class="nav-link ${active === 'main' ? 'active' : ''}" href="main.html"><i class="bi bi-house-door me-1"></i>Главная</a></li>
          <li class="nav-item"><a class="nav-link ${active === 'clients_physical' ? 'active' : ''}" href="clients_physical.html"><i class="bi bi-people me-1"></i>Физ. лица</a></li>
          <li class="nav-item"><a class="nav-link ${active === 'companies' ? 'active' : ''}" href="companies_list.html"><i class="bi bi-building me-1"></i>Компании</a></li>
          <li class="nav-item"><a class="nav-link ${active === 'projects' ? 'active' : ''}" href="projects_list.html"><i class="bi bi-kanban me-1"></i>Проекты</a></li>
          ${showAdmin ? `<li class="nav-item"><a class="nav-link ${active === 'admin' ? 'active' : ''}" href="admin.html"><i class="bi bi-shield-lock me-1"></i>Админ</a></li>` : ''}
        </ul>
        <div class="d-flex align-items-center gap-2 mt-3 mt-lg-0">
          ${userName ? `<span class="navbar-user-pill d-none d-md-inline-flex"><i class="bi bi-person-circle"></i>${escapeHtml(userName)}</span>` : ''}
          <button class="btn btn-outline-light btn-sm" id="logoutBtn"><i class="bi bi-box-arrow-right me-1"></i>Выйти</button>
        </div>
      </div>
    </div>
  </nav>`;

  document.getElementById('logoutBtn').addEventListener('click', async () => {
    await api.logout();
    window.location.href = 'login.html';
  });

  if (typeof ensureBootstrapBundle === 'function') ensureBootstrapBundle();
}
