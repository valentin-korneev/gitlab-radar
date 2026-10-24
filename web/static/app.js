const API = {
  dashboard: '/api/dashboard/',
  projects: '/api/project/',
  scan: '/api/scan/',
};

const PAGE_TITLES = {
  dashboard: 'Dashboard',
  projects: 'Проекты',
  admin: 'Admin',
};

const state = {
  projects: [],
  selectedId: null,
  selectedSubprojectPath: null,
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

function projectPathParts(value) {
  return value.split('/').filter(Boolean);
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function subprojectView(project, subproject, detected = true) {
  const isRoot = subproject.path === '.';
  return {
    path: subproject.path,
    title: isRoot ? project.name : projectPathParts(subproject.path).at(-1),
    fullPath: isRoot ? project.path_with_namespace : `${project.path_with_namespace}/${subproject.path}`,
    packageManager: subproject.package_manager,
    isRoot,
    detected,
  };
}

function projectView(project) {
  const subprojects = project.subprojects.map((subproject) => subprojectView(project, subproject));
  const root = subprojects.find((subproject) => subproject.isRoot) || null;
  const monorepository = subprojects.length > 1;
  const fallback = subprojects.length === 0
    ? subprojectView(project, { path: '.', package_manager: project.package_manager }, false)
    : null;
  return {
    project,
    root: root || (monorepository ? null : subprojects[0]) || fallback,
    children: monorepository ? subprojects.filter((subproject) => !subproject.isRoot) : [],
    monorepository,
  };
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
    `${project.name} ${project.path_with_namespace} ${project.subprojects.map((item) => item.path).join(' ')}`
      .toLowerCase()
      .includes(query),
  );
  const list = document.querySelector('#project-list');
  list.replaceChildren();

  if (!projects.length) {
    const empty = element(
      'p',
      'empty-state',
      query ? 'Проекты не найдены.' : 'Список проектов пуст. Запустите сканирование.',
    );
    list.append(empty);
    return;
  }

  projects.forEach((project) => {
    const view = projectView(project);
    const selectedProject = project.id === state.selectedId;
    const tree = element('div', 'project-tree');
    const row = element('button');
    const parentActive = selectedProject && state.selectedSubprojectPath === (view.root?.path || null);
    row.className = `project-row${parentActive ? ' active' : ''}`;
    row.type = 'button';

    const identity = element('span');
    const name = element('strong', '', project.name);
    const path = element('small', '', projectPathParts(project.path_with_namespace).join(' › '));
    identity.append(name, path);
    if (view.monorepository) {
      const subprojects = element(
        'small',
        'subproject-summary',
        `Монорепозиторий · подпроектов: ${view.children.length}`,
      );
      identity.append(subprojects);
    }

    const activity = element('time', '', formatDate(project.last_activity_at));
    row.append(identity, activity);
    row.addEventListener('click', () => selectProject(view, view.root, row));
    tree.append(row);

    if (view.children.length) {
      const children = element('div', 'project-children');
      view.children.forEach((subproject) => {
        const child = element('button');
        const childActive = selectedProject && state.selectedSubprojectPath === subproject.path;
        child.className = `project-child${childActive ? ' active' : ''}`;
        child.type = 'button';
        const childPath = element('span', '', projectPathParts(subproject.path).join(' › '));
        child.append(childPath, packageManagerBadge(subproject.packageManager));
        child.addEventListener('click', () => selectProject(view, subproject, child));
        children.append(child);
      });
      tree.append(children);
    }

    list.append(tree);
  });
}

function appendDetail(container, label, value) {
  const title = element('p', 'detail-label', label);
  const content = value instanceof Node ? value : element('p', 'detail-value', value || '—');
  container.append(title, content);
  return content;
}

function appendProjectPath(container, value) {
  const breadcrumb = element('div', 'project-path');
  projectPathParts(value).forEach((part) => {
    breadcrumb.append(element('span', '', part));
  });
  appendDetail(container, 'Полный путь', breadcrumb);
}

function packageManagerBadge(value) {
  const badge = element('span', 'status-badge', value || '—');
  badge.classList.add(value === 'uv' ? 'compliant' : 'non-compliant');
  return badge;
}

function renderProjectDetail(view, subproject) {
  const { project } = view;
  const detail = document.querySelector('#project-detail');
  detail.replaceChildren();

  if (!subproject) {
    detail.append(
      element('h3', '', project.name),
      element('p', 'empty-state', 'В корне репозитория pyproject.toml не найден. Выберите подпроект.'),
    );
    return;
  }

  detail.append(element('h3', '', subproject.title));
  appendDetail(detail, 'ID', String(project.id));
  appendProjectPath(detail, subproject.fullPath);
  appendDetail(detail, 'Основная ветка', project.default_branch);
  appendDetail(detail, 'Пакетный менеджер', packageManagerBadge(subproject.packageManager));
  appendDetail(detail, 'Последняя активность', formatDate(project.last_activity_at));

  const link = element('a', 'detail-link', 'Открыть в GitLab →');
  link.href = project.web_url;
  link.target = '_blank';
  link.rel = 'noreferrer';
  detail.append(link);
}

function selectProject(view, subproject, row) {
  state.selectedId = view.project.id;
  state.selectedSubprojectPath = subproject?.path || null;
  document.querySelectorAll('.project-row.active, .project-child.active')
    .forEach((element) => element.classList.remove('active'));
  row.classList.add('active');
  renderProjectDetail(view, subproject);
}

function renderDashboard(dashboard) {
  document.querySelector('#project-count').textContent = dashboard.projects_count;

  const statistics = document.querySelector('#package-manager-stats');
  statistics.replaceChildren();
  dashboard.package_managers.forEach((item) => {
    const row = element('div', 'statistics-row');
    const label = element('div', 'statistics-label');
    label.append(element('strong', '', item.title), element('span', '', `${item.percentage}%`));
    const track = element('div', 'statistics-track');
    const trackValue = element('span');
    trackValue.style.width = `${item.percentage}%`;
    track.append(trackValue);
    row.append(label, track, element('b', '', item.projects_count));
    statistics.append(row);
  });

  const requirements = document.querySelector('#company-requirements');
  requirements.replaceChildren();
  dashboard.company_requirements.forEach((item) => {
    const card = element('div', 'requirement');
    const header = element('div');
    header.append(
      element('strong', '', item.title),
      element('b', '', `${item.compliance_percentage}%`),
    );
    const progress = element('div', 'requirement-progress');
    const progressValue = element('span');
    progressValue.style.width = `${item.compliance_percentage}%`;
    progress.append(progressValue);
    card.append(
      header,
      element('p', '', item.description),
      progress,
      element('small', '', `${item.matching_projects} из ${item.total_projects} проектов`),
    );
    requirements.append(card);
  });
}

async function loadDashboard() {
  renderDashboard(await api(API.dashboard));
}

async function loadProjects() {
  state.projects = await api(API.projects);
  renderProjects(document.querySelector('#project-search').value);

  const selected = state.projects.find((project) => project.id === state.selectedId);
  if (selected) {
    const view = projectView(selected);
    const entries = [view.root, ...view.children].filter(Boolean);
    const subproject = entries.find((item) => item.path === state.selectedSubprojectPath) || view.root;
    state.selectedSubprojectPath = subproject?.path || null;
    renderProjectDetail(view, subproject);
  }
}

function renderScanStatus(scan) {
  document.querySelector('#scan-state').textContent = scan.state_title;
  document.querySelector('#scan-button').disabled = scan.state === 'running';
  document.querySelector('#scan-dot').className = scan.state;

  let description = 'Сканирование ещё не запускалось.';
  if (scan.state === 'running') description = `Запущено ${formatDate(scan.started_at)}`;
  if (scan.state === 'completed') {
    description = `Завершено ${formatDate(scan.completed_at)} · проектов: ${scan.projects_count}`;
    if (scan.errors.length) description += ` · ошибок: ${scan.errors.length}`;
  }
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

    if (previousState === 'running' && scan.state === 'completed') {
      await Promise.all([loadDashboard(), loadProjects()]);
    }
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
Promise.all([loadDashboard(), loadProjects(), refreshScanStatus()]).catch(showError);
