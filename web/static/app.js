const API = {
  projects: '/api/project/',
  scan: '/api/scan/',
};

const PAGE_TITLES = {
  dashboard: 'Dashboard',
  projects: 'Проекты',
  admin: 'Admin',
};

const SCAN_LABELS = {
  idle: 'Ожидание',
  running: 'Выполняется',
  completed: 'Завершено',
  failed: 'Ошибка',
};

const state = {
  projects: [],
  selectedId: null,
  scanState: null,
  pollTimer: null,
};

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

function formatDate(value) {
  if (!value) return '—';
  return new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));
}

function showPage() {
  const requestedPage = window.location.hash.slice(1);
  const pageName = PAGE_TITLES[requestedPage] ? requestedPage : 'dashboard';
  document.querySelectorAll('.nav-item, .page').forEach((element) => element.classList.remove('active'));
  document.querySelector(`.nav-item[data-page="${pageName}"]`).classList.add('active');
  document.querySelector(`#${pageName}`).classList.add('active');
  document.querySelector('#page-title').textContent = PAGE_TITLES[pageName];
}

function renderProjects(filter = '') {
  const query = filter.trim().toLowerCase();
  const projects = state.projects.filter((project) =>
    `${project.name} ${project.path_with_namespace}`.toLowerCase().includes(query),
  );
  const list = document.querySelector('#project-list');
  list.replaceChildren();

  if (!projects.length) {
    const empty = document.createElement('p');
    empty.className = 'empty-state';
    empty.textContent = query ? 'Проекты не найдены.' : 'Список проектов пуст. Запустите сканирование.';
    list.append(empty);
    return;
  }

  projects.forEach((project) => {
    const row = document.createElement('button');
    row.className = `project-row${project.id === state.selectedId ? ' active' : ''}`;
    row.type = 'button';

    const identity = document.createElement('span');
    const name = document.createElement('strong');
    name.textContent = project.name;
    const path = document.createElement('small');
    path.textContent = project.path_with_namespace;
    identity.append(name, path);

    const activity = document.createElement('time');
    activity.textContent = formatDate(project.last_activity_at);
    row.append(identity, activity);
    row.addEventListener('click', () => selectProject(project, row));
    list.append(row);
  });
}

function appendDetail(container, label, value) {
  const title = document.createElement('p');
  title.className = 'detail-label';
  title.textContent = label;
  const content = document.createElement('p');
  content.className = 'detail-value';
  content.textContent = value || '—';
  container.append(title, content);
}

function renderProjectDetail(project) {
  const detail = document.querySelector('#project-detail');
  detail.replaceChildren();
  const title = document.createElement('h3');
  title.textContent = project.name;
  detail.append(title);
  appendDetail(detail, 'ID', String(project.id));
  appendDetail(detail, 'Полный путь', project.path_with_namespace);
  appendDetail(detail, 'Основная ветка', project.default_branch);
  appendDetail(detail, 'Последняя активность', formatDate(project.last_activity_at));

  const link = document.createElement('a');
  link.className = 'detail-link';
  link.href = project.web_url;
  link.target = '_blank';
  link.rel = 'noreferrer';
  link.textContent = 'Открыть в GitLab →';
  detail.append(link);
}

function selectProject(project, row) {
  state.selectedId = project.id;
  document.querySelector('.project-row.active')?.classList.remove('active');
  row.classList.add('active');
  renderProjectDetail(project);
}

async function loadProjects() {
  state.projects = await api(API.projects);
  document.querySelector('#project-count').textContent = state.projects.length;
  renderProjects(document.querySelector('#project-search').value);

  const selected = state.projects.find((project) => project.id === state.selectedId);
  if (selected) renderProjectDetail(selected);
}

function renderScanStatus(scan) {
  document.querySelector('#scan-state').textContent = SCAN_LABELS[scan.state];
  document.querySelector('#scan-button').disabled = scan.state === 'running';
  document.querySelector('#scan-dot').className = scan.state;

  let description = 'Сканирование ещё не запускалось.';
  if (scan.state === 'running') description = `Запущено ${formatDate(scan.started_at)}`;
  if (scan.state === 'completed') description = `Завершено ${formatDate(scan.completed_at)} · проектов: ${scan.projects_count}`;
  if (scan.state === 'failed') description = `Завершено ${formatDate(scan.completed_at)} · ${scan.error}`;
  document.querySelector('#scan-description').textContent = description;
}

async function refreshScanStatus() {
  try {
    const previousState = state.scanState;
    const scan = await api(API.scan);
    state.scanState = scan.state;
    renderScanStatus(scan);

    window.clearTimeout(state.pollTimer);
    state.pollTimer = scan.state === 'running'
      ? window.setTimeout(refreshScanStatus, 1200)
      : null;

    if (previousState === 'running' && scan.state === 'completed') await loadProjects();
  } catch (error) {
    showError(error);
  }
}

function showError(error) {
  const toast = document.querySelector('#global-error');
  toast.textContent = error.message;
  toast.hidden = false;
  window.setTimeout(() => { toast.hidden = true; }, 5000);
}

document.querySelectorAll('.nav-item').forEach((item) => {
  item.addEventListener('click', () => { window.location.hash = item.dataset.page; });
});

window.addEventListener('hashchange', showPage);
document.querySelector('#project-search').addEventListener('input', (event) => renderProjects(event.target.value));

document.querySelector('#scan-button').addEventListener('click', async () => {
  try {
    await api(API.scan, { method: 'POST' });
    await refreshScanStatus();
  } catch (error) {
    showError(error);
    await refreshScanStatus();
  }
});

showPage();
Promise.all([loadProjects(), refreshScanStatus()]).catch(showError);
