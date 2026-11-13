function formatDate(value) {
  if (!value) return '—';
  return new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));
}
function formatDuration(seconds) {
  const roundedSeconds = Math.max(0, Math.round(seconds));
  if (roundedSeconds < 60) return `${roundedSeconds.toLocaleString('ru-RU')} сек.`;
  return `${Math.floor(roundedSeconds / 60)} мин. ${roundedSeconds % 60} сек.`;
}
function projectPathParts(value) { return value.split('/').filter(Boolean); }
function normalizePythonVersion(value) {
  const match = value?.match(/(?:^|\D)(\d+)\.(\d+)/);
  return match ? `${match[1]}.${match[2]}` : null;
}
function canonicalLanguageCode(code) {
  return ['javascript', 'typescript'].includes(code) ? 'javascript' : code;
}
function languageDisplayName(code, name = null) {
  return canonicalLanguageCode(code) === 'javascript' ? 'JS / TS' : name || code;
}
function maskWebhookText(value) {
  return String(value || '');
}
function webhookDomain(value) {
  try {
    const url = new URL(value.includes('://') ? value : `https://${value}`);
    return `${url.hostname}${url.port ? `:${url.port}` : ''}`.toLowerCase();
  }
  catch (error) { return 'unknown-domain'; }
}
function maskWebhookUrl(value) { return String(value || ''); }
function registryName(value) {
  try { return new URL(value.includes('://') ? value : `https://${value}`).host.toLowerCase(); }
  catch (error) { return value.split('/')[0].toLowerCase(); }
}
function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
const ICON_PATHS = {
  refresh: '<path d="M3 12a9 9 0 0 1 15.36-6.36L21 8M21 3v5h-5M21 12a9 9 0 0 1-15.36 6.36L3 16M8 16H3v5"/>',
  history: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  close: '<path d="M6 6l12 12M18 6 6 18"/>',
  edit: '<path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4Z"/>',
  move: '<path d="m9 5-5 5 5 5M4 10h10a6 6 0 0 1 6 6v3"/>',
  trash: '<path d="M4 7h16M9 7V4h6v3M7 7l1 13h8l1-13M10 11v5M14 11v5"/>',
  group: '<path d="M8 4H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h3M16 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M8 12h8M12 8v8"/>',
  filter: '<path d="M4 5h16l-6 7v5l-4 2v-7Z"/>',
  download: '<path d="M12 3v12M7 10l5 5 5-5M5 21h14"/>',
  star: '<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3 1.1-6.2L3 9.6l6.2-.9Z"/>',
};
function iconElement(name) {
  const holder = document.createElement('span');
  holder.innerHTML = `<svg class="button-icon" viewBox="0 0 24 24" aria-hidden="true">${ICON_PATHS[name]}</svg>`;
  return holder.firstElementChild;
}
function iconButton(icon, className, title) {
  const button = element('button', `${className} icon-button`);
  button.type = 'button';
  button.title = title;
  button.setAttribute('aria-label', title);
  button.append(iconElement(icon));
  return button;
}
function initializeIcons() {
  initializeIconTooltips();
  document.querySelectorAll('[data-icon]').forEach((button) => button.append(iconElement(button.dataset.icon)));
}
function confirmAction(title, message, confirmLabel = 'Подтвердить действие') {
  const dialog = document.querySelector('#confirm-dialog');
  const submit = document.querySelector('#confirm-dialog-submit');
  document.querySelector('#confirm-dialog-title').textContent = title;
  document.querySelector('#confirm-dialog-message').textContent = message;
  submit.title = confirmLabel;
  submit.setAttribute('aria-label', confirmLabel);
  dialog.returnValue = 'cancel';
  dialog.showModal();
  return new Promise((resolve) => {
    dialog.addEventListener('close', () => resolve(dialog.returnValue === 'confirm'), { once: true });
  });
}

export { canonicalLanguageCode, confirmAction, element, formatDate, formatDuration, iconButton, iconElement, initializeIcons, languageDisplayName, maskWebhookText, maskWebhookUrl, projectPathParts, registryName, webhookDomain };

function initializeIconTooltips() {
  if (document.documentElement.dataset.iconTooltips) return;
  document.documentElement.dataset.iconTooltips = 'true';
  const tooltip = element('div', 'icon-tooltip');
  tooltip.id = 'icon-tooltip';
  tooltip.setAttribute('role', 'tooltip');
  tooltip.hidden = true;
  const hasPopover = typeof tooltip.showPopover === 'function';
  if (hasPopover) tooltip.setAttribute('popover', 'manual');
  document.body.append(tooltip);
  let active = null;
  let previousDescription = null;
  let previousTitle = null;
  function hide() {
    if (hasPopover && tooltip.matches(':popover-open')) tooltip.hidePopover();
    tooltip.hidden = true;
    if (active) {
      if (previousDescription === null) active.removeAttribute('aria-describedby');
      else active.setAttribute('aria-describedby', previousDescription);
      if (previousTitle !== null) active.setAttribute('title', previousTitle);
    }
    active = null;
  }
  function show(target) {
    if (active === target) return;
    hide();
    const text = target.getAttribute('aria-label');
    if (!text) return;
    active = target;
    previousDescription = target.getAttribute('aria-describedby');
    previousTitle = target.getAttribute('title');
    target.removeAttribute('title');
    target.setAttribute('aria-describedby', [previousDescription, tooltip.id].filter(Boolean).join(' '));
    tooltip.textContent = text;
    // Popovers escape scrolling containers and modal clipping without changing layout.
    if (!hasPopover) (target.closest('dialog') || document.body).append(tooltip);
    tooltip.hidden = false;
    if (hasPopover) tooltip.showPopover();
    const anchor = target.getBoundingClientRect();
    const bounds = tooltip.getBoundingClientRect();
    tooltip.style.left = `${Math.max(8, Math.min(anchor.left, window.innerWidth - bounds.width - 8))}px`;
    const above = anchor.top - bounds.height - 8;
    const top = above >= 8 ? above : anchor.bottom + 8;
    tooltip.style.top = `${Math.max(8, Math.min(top, window.innerHeight - bounds.height - 8))}px`;
  }
  function enter(event) {
    const target = event.target.closest?.('.icon-button[aria-label], .condition-remove[aria-label]');
    if (target) show(target);
  }
  function leave(event) {
    if (active && !active.contains(event.relatedTarget)) hide();
  }
  document.addEventListener('pointerover', enter);
  document.addEventListener('focusin', enter);
  document.addEventListener('pointerout', leave);
  document.addEventListener('focusout', leave);
  document.addEventListener('scroll', hide, true);
  document.addEventListener('click', hide, true);
  window.addEventListener('resize', hide);
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape') hide(); });
}
