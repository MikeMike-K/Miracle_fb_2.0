/**
 * Единый клиент для общения с backend REST API.
 * Меняйте API_BASE, если backend развёрнут на другом адресе/порту.
 */
const API_BASE = window.API_BASE || `${location.protocol}//${location.hostname}:5000`;

async function apiRequest(path, { method = 'GET', body = null } = {}) {
  const opts = {
    method,
    credentials: 'include',
    headers: {},
  };
  if (body !== null) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(`${API_BASE}${path}`, opts);
  let data = null;
  try { data = await res.json(); } catch (e) { /* no body */ }
  if (!res.ok) {
    if (res.status === 401) {
      window.location.href = 'login.html';
    }
    const error = new Error((data && data.error) || `Ошибка запроса (${res.status})`);
    error.data = data;
    throw error;
  }
  return data;
}

const api = {
  login: (username, password) => apiRequest('/api/login', { method: 'POST', body: { username, password } }),
  logout: () => apiRequest('/api/logout', { method: 'POST' }),
  me: () => apiRequest('/api/me'),

  usersList: () => apiRequest('/api/users'),

  adminUsers: () => apiRequest('/api/admin/users'),
  adminCreateUser: (payload) => apiRequest('/api/admin/users', { method: 'POST', body: payload }),
  adminGetUser: (id) => apiRequest(`/api/admin/users/${id}`),
  adminEditUser: (id, payload) => apiRequest(`/api/admin/users/${id}`, { method: 'PUT', body: payload }),
  adminChangePassword: (payload) => apiRequest('/api/admin/change_password', { method: 'POST', body: payload }),

  adminReportsGet: () => apiRequest('/api/admin/reports'),
  adminReportsSave: (payload) => apiRequest('/api/admin/reports/settings', { method: 'POST', body: payload }),
  adminReportsTest: (kind, payload) => apiRequest(`/api/admin/reports/test/${kind}`, { method: 'POST', body: payload || {} }),
  adminReportsDemoSeed: () => apiRequest('/api/admin/reports/demo/seed', { method: 'POST' }),
  adminReportsDemoSend: (kind, payload) => apiRequest(`/api/admin/reports/demo/send/${kind}`, { method: 'POST', body: payload || {} }),
  adminReportsPreview: async (kind) => {
    const res = await fetch(`${API_BASE}/api/admin/reports/preview/${kind}`, { credentials: 'include' });
    if (!res.ok) {
      let data = null;
      try { data = await res.json(); } catch (e) { /* no body */ }
      const error = new Error((data && data.error) || `Ошибка предпросмотра (${res.status})`);
      error.data = data;
      throw error;
    }
    return res.text();
  },
  adminSmtpPasswordsSave: (passwords) => apiRequest('/api/admin/smtp/passwords', { method: 'POST', body: { passwords } }),
  adminSmtpCheck: () => apiRequest('/api/admin/smtp/check', { method: 'POST' }),
  adminSelfCheck: () => apiRequest('/api/admin/self-check'),

  clientsList: () => apiRequest('/api/clients'),
  clientCreate: (payload, companyId) => apiRequest(`/api/clients${companyId ? `?company_id=${companyId}` : ''}`, { method: 'POST', body: payload }),
  clientGet: (id) => apiRequest(`/api/clients/${id}`),
  clientEdit: (id, payload) => apiRequest(`/api/clients/${id}`, { method: 'PUT', body: payload }),
  clientEventAdd: (id, payload) => apiRequest(`/api/clients/${id}/events`, { method: 'POST', body: payload }),
  clientEventComplete: (id, eventId) => apiRequest(`/api/clients/${id}/events/${eventId}/complete`, { method: 'POST' }),
  clientEventCancel: (id, eventId) => apiRequest(`/api/clients/${id}/events/${eventId}/cancel`, { method: 'POST' }),
  clientEventGet: (id, eventId) => apiRequest(`/api/clients/${id}/events/${eventId}`),
  clientEventFinish: (id, eventId, payload) => apiRequest(`/api/clients/${id}/events/${eventId}/finish`, { method: 'POST', body: payload }),
  clientAvailableEmployers: (id) => apiRequest(`/api/clients/${id}/available_employers`),
  clientUnlinkEmployer: (clientId, companyId) => apiRequest(`/api/clients/${clientId}/employers/${companyId}`, { method: 'DELETE' }),

  companiesList: () => apiRequest('/api/companies'),
  companyCreate: (payload, projectId, clientId) => {
    const qs = [];
    if (projectId) qs.push(`project_id=${projectId}`);
    if (clientId) qs.push(`client_id=${clientId}`);
    return apiRequest(`/api/companies${qs.length ? `?${qs.join('&')}` : ''}`, { method: 'POST', body: payload });
  },
  companyGet: (id) => apiRequest(`/api/companies/${id}`),
  companyEdit: (id, payload) => apiRequest(`/api/companies/${id}`, { method: 'PUT', body: payload }),
  companyEventAdd: (id, payload) => apiRequest(`/api/companies/${id}/events`, { method: 'POST', body: payload }),
  companyEventComplete: (id, eventId) => apiRequest(`/api/companies/${id}/events/${eventId}/complete`, { method: 'POST' }),
  companyEventCancel: (id, eventId) => apiRequest(`/api/companies/${id}/events/${eventId}/cancel`, { method: 'POST' }),
  companyEventGet: (id, eventId) => apiRequest(`/api/companies/${id}/events/${eventId}`),
  companyEventFinish: (id, eventId, payload) => apiRequest(`/api/companies/${id}/events/${eventId}/finish`, { method: 'POST', body: payload }),
  companyAvailableEmployees: (id) => apiRequest(`/api/companies/${id}/available_employees`),
  companyLinkEmployee: (id, clientId) => apiRequest(`/api/companies/${id}/employees`, { method: 'POST', body: { client_id: clientId } }),
  companyUnlinkEmployee: (id, clientId) => apiRequest(`/api/companies/${id}/employees/${clientId}`, { method: 'DELETE' }),

  projectsList: () => apiRequest('/api/projects'),
  projectCreate: (payload) => apiRequest('/api/projects', { method: 'POST', body: payload }),
  projectGet: (id) => apiRequest(`/api/projects/${id}`),
  projectEdit: (id, payload) => apiRequest(`/api/projects/${id}`, { method: 'PUT', body: payload }),
  projectEventAdd: (id, payload) => apiRequest(`/api/projects/${id}/events`, { method: 'POST', body: payload }),
  projectEventComplete: (id, eventId) => apiRequest(`/api/projects/${id}/events/${eventId}/complete`, { method: 'POST' }),
  projectEventCancel: (id, eventId) => apiRequest(`/api/projects/${id}/events/${eventId}/cancel`, { method: 'POST' }),
  projectEventGet: (id, eventId) => apiRequest(`/api/projects/${id}/events/${eventId}`),
  projectEventFinish: (id, eventId, payload) => apiRequest(`/api/projects/${id}/events/${eventId}/finish`, { method: 'POST', body: payload }),
  projectAvailableCompanies: (id) => apiRequest(`/api/projects/${id}/available_companies`),
  projectLinkCompany: (id, companyId) => apiRequest(`/api/projects/${id}/companies`, { method: 'POST', body: { company_id: companyId } }),
  projectUnlinkCompany: (id, companyId) => apiRequest(`/api/projects/${id}/companies/${companyId}`, { method: 'DELETE' }),
};

async function requireAuth() {
  try {
    const me = await api.me();
    if (!me.logged_in) {
      window.location.href = 'login.html';
      return null;
    }
    return me;
  } catch (e) {
    window.location.href = 'login.html';
    return null;
  }
}

function showToast(message, type = 'success') {
  const id = 'toast-' + Date.now();
  const wrap = document.getElementById('toast-container') || (() => {
    const d = document.createElement('div');
    d.id = 'toast-container';
    d.style.cssText = 'position:fixed;top:20px;right:20px;z-index:9999;display:flex;flex-direction:column;gap:8px;';
    document.body.appendChild(d);
    return d;
  })();
  const el = document.createElement('div');
  el.id = id;
  el.className = `alert alert-${type === 'error' ? 'danger' : type === 'success' ? 'success' : 'info'}`;
  el.textContent = message;
  wrap.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}
