function formatDate(value) {
  if (!value) return '—';
  return new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));
}
function formatDuration(seconds) {
  if (seconds < 60) return `${seconds.toLocaleString('ru-RU')} сек.`;
  return `${Math.floor(seconds / 60)} мин. ${Math.round(seconds % 60)} сек.`;
}
function projectPathParts(value) { return value.split('/').filter(Boolean); }
function normalizePythonVersion(value) {
  const match = value?.match(/(?:^|\D)(\d+)\.(\d+)/);
  return match ? `${match[1]}.${match[2]}` : null;
}
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
  plus: '<path d="M12 5v14M5 12h14"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  close: '<path d="M6 6l12 12M18 6 6 18"/>',
  edit: '<path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4Z"/>',
  move: '<path d="m9 5-5 5 5 5M4 10h10a6 6 0 0 1 6 6v3"/>',
  trash: '<path d="M4 7h16M9 7V4h6v3M7 7l1 13h8l1-13M10 11v5M14 11v5"/>',
  group: '<path d="M8 4H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h3M16 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M8 12h8M12 8v8"/>',
  filter: '<path d="M4 5h16l-6 7v5l-4 2v-7Z"/>',
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
document.querySelectorAll('[data-icon]').forEach((button) => button.append(iconElement(button.dataset.icon)));
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
