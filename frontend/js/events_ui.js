function eventsBlockHtml(planned, completed, cancelled, baseUrl, ctx, parentId) {
  const finishUrl = (eventId) =>
    `edit_event.html?ctx=${encodeURIComponent(ctx)}&parent_id=${encodeURIComponent(parentId)}&event_id=${eventId}`;

  const row = (e, status) => `
    <div class="event-list-item">
      <div class="d-flex justify-content-between">
        <div>
          <strong>${escapeHtml(e.event_type)}</strong>
          <span class="text-muted small"> — ${escapeHtml(e.start_date || '')}</span><br>
          <span class="small">${escapeHtml(e.description || '')}</span>
          ${e.responsible_user ? `<br><span class="text-muted small">Ответственный: ${escapeHtml(e.responsible_user)}</span>` : ''}
          ${status === 'completed' ? `
            <br><span class="small status-completed">Результат: ${escapeHtml(e.result || '-')}</span>
            ${e.completion_desc ? `<br><span class="small text-muted">${escapeHtml(e.completion_desc)}</span>` : ''}
            ${e.rating ? `<br><span class="small">Оценка: ${escapeHtml(String(e.rating))}/5</span>` : ''}
          ` : ''}
        </div>
        <div class="text-nowrap ms-2">
          ${status === 'planned' ? `
            <a class="btn btn-sm btn-success" href="${finishUrl(e.id)}" title="Завершить с результатом">Завершить</a>
            <button class="btn btn-sm btn-outline-danger" onclick="cancelEvent(${e.id})" title="Отменить">✕</button>
          ` : ''}
          <a class="btn btn-sm btn-outline-secondary" href="${baseUrl}&event_id=${e.id}">Открыть</a>
        </div>
      </div>
    </div>`;

  const section = (title, items, status, cls) => `
    <h6 class="${cls} mt-3">${title} (${items.length})</h6>
    ${items.length ? items.map(e => row(e, status)).join('') : '<p class="text-muted small">Нет мероприятий</p>'}
  `;

  return `
    ${section('Запланировано', planned, 'planned', 'status-planned')}
    ${section('Выполнено', completed, 'completed', 'status-completed')}
    ${section('Отменено', cancelled, 'cancelled', 'status-cancelled')}
  `;
}
