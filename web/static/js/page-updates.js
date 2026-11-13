import { API, PAGE_ROUTES, STATE_CHANNEL } from './config.js';
import { invalidateReads } from './requests.js';
import { showError } from './toasts.js';
import { confirmAction } from './shared.js';
import { state } from './state.js';

const editablePages = new Set(['requirements', 'parameters', 'languages', 'users', 'visibility', 'visibility-admin', 'blacklist', 'admin']);
const pageEdits = new Map();
function pageEdit(page) {
  if (!pageEdits.has(page)) pageEdits.set(page, { dirty: false, stale: false });
  return pageEdits.get(page);
}
function activePageName() { return PAGE_ROUTES[state.currentRoute]?.page; }
function renderPageNotice() {
  const notice = document.querySelector('#page-update-notice');
  notice.hidden = !pageEdit(activePageName()).stale;
}
function markPagesChanged(pages, external = true) {
  pages.forEach((page) => {
    state.loaded[page] = false;
    if (external) pageEdit(page).stale = true;
  });
  renderPageNotice();
}
function invalidateFromMutation(path, external = false) {
  if (path.startsWith(`${API.scan}schedules`)) {
    invalidateReads();
    markPagesChanged(['admin'], external);
    return;
  }
  let pages = [];
  if (path.startsWith(API.requirements) || path.startsWith(API.requirementGroups)) {
    pages = ['dashboard', 'projects', 'requirements'];
    state.requirementCatalog = null;
  } else if (path.startsWith(API.parameters)) {
    pages = ['dashboard', 'projects', 'requirements', 'parameters'];
    state.requirementCatalog = null;
  } else if (path.startsWith(API.programmingLanguages)) {
    pages = ['dashboard', 'projects', 'dependencies', 'requirements', 'languages'];
    state.requirementCatalog = null;
  } else if (path.startsWith(API.projectBlacklist)) {
    pages = ['dashboard', 'projects', 'dependencies', 'blacklist'];
  } else if (path.startsWith(API.visibility)) {
    pages = ['dashboard', 'projects', 'dependencies', 'visibility', 'visibility-admin'];
  } else if (path.startsWith(API.authorizedUsers)) pages = ['users'];
  if (!pages.length) return;
  invalidateReads();
  state.dependencyCache = {};
  markPagesChanged(pages, external);
}
async function refreshChangedPage() {
  const page = activePageName();
  if (pageEdit(page).dirty && !await confirmAction(
    'Обновить страницу', 'Несохраненные изменения этой страницы будут потеряны.', 'Обновить',
  )) return;
  if (page !== activePageName()) return;
  // A full reload also refreshes shared resources and closes editors deliberately.
  window.location.reload();
}
function initializePageUpdates() {
  document.addEventListener('input', () => {
    const page = activePageName();
    if (editablePages.has(page)) pageEdit(page).dirty = true;
  });
  document.addEventListener('change', () => {
    const page = activePageName();
    if (editablePages.has(page)) pageEdit(page).dirty = true;
  });
  document.querySelector('#page-update-reload').addEventListener('click', () => refreshChangedPage().catch(showError));
  window.addEventListener('radar-mutation', (event) => invalidateFromMutation(event.detail.path));
  STATE_CHANNEL?.addEventListener('message', (event) => invalidateFromMutation(event.data?.path || '', true));
}

export { editablePages, initializePageUpdates, invalidateFromMutation, pageEdit, renderPageNotice };
