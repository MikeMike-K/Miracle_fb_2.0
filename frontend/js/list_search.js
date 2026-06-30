/** Клиентский поиск по спискам (без запросов на сервер). */

function filterBySearch(items, query, getSearchText) {
  const q = (query || '').trim().toLowerCase();
  if (!q) return items;
  return items.filter((item) => getSearchText(item).toLowerCase().includes(q));
}

function updateSearchCount(el, shown, total) {
  if (!el) return;
  if (!total) {
    el.textContent = '';
    return;
  }
  el.textContent = shown === total ? `Всего: ${total}` : `Показано: ${shown} из ${total}`;
}

/**
 * @param {object} opts
 * @param {string} opts.inputId
 * @param {string} [opts.countId]
 * @param {() => any[]} opts.getItems
 * @param {(filtered: any[]) => void} opts.render
 * @param {(item: any) => string} opts.searchText
 * @returns {() => void} refresh — вызвать после перезагрузки данных
 */
function setupListSearch({ inputId, countId, getItems, render, searchText }) {
  const input = document.getElementById(inputId);
  const count = countId ? document.getElementById(countId) : null;
  if (!input) return () => {};

  const apply = () => {
    const all = getItems();
    const filtered = filterBySearch(all, input.value, searchText);
    render(filtered);
    updateSearchCount(count, filtered.length, all.length);
  };

  input.addEventListener('input', apply);
  apply();
  return apply;
}

function filterEventsBySearch(events, query) {
  const q = (query || '').trim().toLowerCase();
  if (!q) return events;
  return events.filter((e) =>
    [e.event_type, e.description, e.responsible_user, e.result, e.completion_desc, e.start_date, e.status]
      .some((v) => String(v || '').toLowerCase().includes(q))
  );
}

function filterRecipientRows(container, query) {
  const q = (query || '').trim().toLowerCase();
  container.querySelectorAll('.form-check').forEach((row) => {
    const text = (row.textContent || '').toLowerCase();
    row.style.display = !q || text.includes(q) ? '' : 'none';
  });
}

/** Поиск по блокам мероприятий на карточках компании/клиента/проекта. */
function setupEventsSearch({ inputId, countId, listId, getEvents, baseUrl, ctx, parentId }) {
  const input = document.getElementById(inputId);
  const count = countId ? document.getElementById(countId) : null;
  const list = document.getElementById(listId);
  if (!input || !list) return () => {};

  const apply = () => {
    const { planned, completed, cancelled } = getEvents();
    const fp = filterEventsBySearch(planned, input.value);
    const fc = filterEventsBySearch(completed, input.value);
    const fx = filterEventsBySearch(cancelled, input.value);
    list.innerHTML = eventsBlockHtml(fp, fc, fx, baseUrl, ctx, parentId);
    const total = planned.length + completed.length + cancelled.length;
    updateSearchCount(count, fp.length + fc.length + fx.length, total);
  };

  input.addEventListener('input', apply);
  apply();
  return apply;
}
