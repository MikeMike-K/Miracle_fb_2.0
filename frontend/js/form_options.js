const FORM_OPTIONS = {
  countries: ['Россия', 'Казахстан', 'Беларусь', 'Китай', 'США', 'Германия', 'Другая'],
  companyActivities: [
    'Airport', 'Car & Machinery industry', 'Chemical & materials production', 'Construction',
    'Design & engineering', 'Developer & Operator', 'Food industry - meat, milk, etc.',
    'Gas & Oil industry', 'High class shopping malls', 'Hospitals and clinics', 'Hotel building 4-5*',
    'Hygienic products - diapers, etc.', 'IT & electronic production', 'Mining & Metallurgical industry',
    'Office building class A', 'Pharmaceutical industry',
  ],
  companyTypes: ['КЛИЕНТ', 'КОНКУРЕНТ', 'ПАРТНЕР', 'ПОСТАВЩИК', 'ПРОЕКТИРОВЩИК'],
  projectTypes: [
    'Equipment Supply services',
    'Facility Management Services',
    'General Contractor functions',
    'Utilities Installations',
  ],
  projectStatuses: [
    'S1. First contact', 'S2. Meeting', 'S3. Ongoing tender',
    'S4. WIN', 'S5. LOST', 'S6. No way',
  ],
  regions: [
    'Москва', 'Московская область', 'Санкт-Петербург', 'Ленинградская область',
    'Центральный федеральный округ', 'Северо-Западный федеральный округ',
    'Южный федеральный округ', 'Северо-Кавказский федеральный округ',
    'Приволжский федеральный округ', 'Уральский федеральный округ',
    'Сибирский федеральный округ', 'Дальневосточный федеральный округ',
    'Республика Татарстан', 'Республика Башкортостан', 'Краснодарский край',
    'Свердловская область', 'Новосибирская область', 'Ростовская область',
    'Казахстан', 'Беларусь', 'Другой регион',
  ],
  currencies: [
    { code: 'RUB', label: '₽ рубль' },
    { code: 'EUR', label: '€ евро' },
    { code: 'USD', label: '$ доллар' },
    { code: 'CNY', label: '¥ юань' },
    { code: 'KZT', label: '₸ тенге' },
    { code: 'BYN', label: 'Br бел. рубль' },
  ],
  eventTypes: [
    'М2. Звонок/Письмо', 'М3. Встреча с клиентом', 'М4. Встреча с партнером',
    'М5. Получение запроса КП', 'М6. Изменение запроса КП', 'М7. Отправка КП',
    'М7.1. Повторная отправка КП', 'М8. Получение заказа',
  ],
  eventResults: [
    'R1. Назначен звонок',
    'R2. Назначена встреча',
    'R3. Назначен запрос КП',
    'No way',
  ],
};

function buildSelectHtml(items, placeholder, current) {
  const val = current || '';
  let html = `<option value="">${escapeHtml(placeholder)}</option>`;
  const seen = new Set();
  for (const item of items) {
    seen.add(item);
    html += `<option value="${escapeHtml(item)}"${item === val ? ' selected' : ''}>${escapeHtml(item)}</option>`;
  }
  if (val && !seen.has(val)) {
    html += `<option value="${escapeHtml(val)}" selected>${escapeHtml(val)}</option>`;
  }
  return html;
}

function setFormSelect(form, name, items, placeholder, value) {
  const el = form.elements[name];
  if (!el || el.tagName !== 'SELECT') return;
  el.innerHTML = buildSelectHtml(items, placeholder, value);
}

function initCurrencySelect(selectEl, current = 'RUB') {
  if (!selectEl) return;
  const val = current || 'RUB';
  selectEl.innerHTML = FORM_OPTIONS.currencies.map((c) =>
    `<option value="${c.code}"${c.code === val ? ' selected' : ''}>${escapeHtml(c.label)}</option>`
  ).join('');
}

function currencySymbol(code) {
  const c = FORM_OPTIONS.currencies.find((x) => x.code === code);
  if (!c) return code || '₽';
  return c.label.split(' ')[0];
}

function initEventTypeSelect(selectEl) {
  if (!selectEl) return;
  selectEl.innerHTML = buildSelectHtml(FORM_OPTIONS.eventTypes, 'Вид мероприятия...', '');
}

function initEventResultSelect(selectEl, current = '') {
  if (!selectEl) return;
  selectEl.innerHTML = buildSelectHtml(FORM_OPTIONS.eventResults, 'Выберите результат...', current);
}

function initEventFormToggle(buttonId = 'toggleEventFormBtn', panelId = 'newEventForm') {
  const btn = document.getElementById(buttonId);
  const panel = document.getElementById(panelId);
  if (!btn || !panel) return;
  btn.addEventListener('click', () => {
    const hidden = panel.classList.toggle('d-none');
    btn.textContent = hidden ? '+ Новое мероприятие' : '− Скрыть форму';
  });
}

/** www.example.ru → https://www.example.ru */
function normalizeWebsite(value) {
  const v = (value || '').trim();
  if (!v) return '';
  if (/^https?:\/\//i.test(v)) return v;
  return `https://${v}`;
}
