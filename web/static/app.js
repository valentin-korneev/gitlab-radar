const API = {
  dashboard: '/api/dashboard/', dependencies: '/api/dependency/', projects: '/api/project/', scan: '/api/scan/',
  requirements: '/api/company-requirement/', requirementCatalog: '/api/company-requirement/catalog',
  requirementGroups: '/api/company-requirement-group/',
  parameters: '/api/application-parameter/',
};
const PAGE_ROUTES = {
  dashboard: { page: 'dashboard' },
  projects: { page: 'projects' },
  dependencies: { page: 'dependencies', source: 'python', title: 'Зависимости', search: 'Найти зависимость' },
  images: { page: 'dependencies', source: 'docker', title: 'Образы контейнеров', search: 'Найти образ' },
  components: { page: 'dependencies', source: 'ci', title: 'CI-компоненты', search: 'Найти компонент' },
  webhooks: { page: 'dependencies', source: 'webhook', title: 'Webhooks', search: 'Найти webhook' },
  requirements: { page: 'requirements' },
  parameters: { page: 'parameters' },
  admin: { page: 'admin' },
};
const SOURCE_ROUTES = { python: 'dependencies', docker: 'images', ci: 'components', webhook: 'webhooks' };
const LEVEL_TITLES = { direct: 'Прямая', optional: 'Опциональная', transitive: 'Транзитивная' };
const HOOK_EVENT_TITLES = {
  push: 'push', tag_push: 'tag push', issues: 'issues', confidential_issues: 'confidential issues',
  merge_requests: 'merge requests', note: 'comments', confidential_note: 'confidential comments',
  job: 'jobs', pipeline: 'pipelines', wiki_page: 'wiki', deployment: 'deployments', releases: 'releases',
  milestone: 'milestones', feature_flag: 'feature flags', resource_access_token: 'access tokens',
  resource_deploy_token: 'deploy tokens',
};
const PHASE_TITLES = {
  idle: 'Ожидание запуска', collecting: 'Сбор файлов из GitLab', analyzing: 'Локальный анализ файлов',
  publishing: 'Публикация результатов', completed: 'Результаты опубликованы',
};
const state = {
  projects: [], dependencies: [], dependencyCache: {}, dependencySource: 'python', selectedId: null, selectedSubprojectPath: null,
  selectedDependency: null, showTransitive: false, scanState: null, scanStatus: null,
  scanSocket: null, scanReconnectTimer: null,
  technologyTarget: null, projectsCount: 0, showSingleTechnologies: false,
  requirements: [], requirementGroups: [], requirementCatalog: null,
  parameters: [],
  selectedRequirementGroupId: null,
  loaded: { dashboard: false, projects: false, dependencies: false, requirements: false, parameters: false, admin: false }, loading: {},
};

async function api(path, options = {}) {
  const response = await fetch(path, { cache: 'no-store', ...options });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `HTTP ${response.status}`);
  }
  return response.status === 204 ? null : response.json();
}
function activeRequirements() { return state.requirements.filter((requirement) => requirement.enabled); }
async function ensureRequirements() {
  const requests = [];
  if (!state.requirements.length) requests.push(api(API.requirements).then((items) => { state.requirements = items; }));
  if (!state.requirementGroups.length) requests.push(api(API.requirementGroups).then((items) => { state.requirementGroups = items; }));
  if (!state.requirementCatalog) requests.push(api(API.requirementCatalog).then((catalog) => { state.requirementCatalog = catalog; }));
  await Promise.all(requests);
  renderRuleFilters();
}
function renderRuleFilters() {
  const container = document.querySelector('.rule-switches');
  const selected = new Set([...container.querySelectorAll('input:checked')].map((input) => input.dataset.rule));
  const heading = container.querySelector('.control-label') || element('span', 'control-label', 'Нарушения правил');
  container.replaceChildren(heading);
  const active = activeRequirements();
  const grouped = state.requirementGroups
    .map((group) => active.filter((requirement) => requirement.group_id === group.id))
    .filter((requirements) => requirements.length);
  container.classList.toggle('six-columns', grouped.length > 4);
  grouped.flat().forEach((requirement) => {
    const label = element('label', 'switch');
    const input = element('input');
    input.type = 'checkbox';
    input.dataset.rule = requirement.code;
    input.checked = selected.has(requirement.code);
    input.addEventListener('change', renderProjects);
    label.append(input, element('span'), document.createTextNode(requirement.title));
    container.append(label);
  });
}
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
function subprojectView(project, subproject, detected = true) {
  const isRoot = subproject.path === '.';
  return {
    path: subproject.path,
    title: isRoot ? project.name : projectPathParts(subproject.path).at(-1),
    fullPath: isRoot ? project.path_with_namespace : `${project.path_with_namespace}/${subproject.path}`,
    packageManager: subproject.package_manager,
    pythonVersion: subproject.python_version || null,
    pythonConstraint: subproject.python_constraint || null,
    pythonVersionSource: subproject.python_version_source || null,
    dependencies: subproject.dependencies || [],
    optionalDependencies: subproject.optional_dependencies || [],
    transitiveDependencies: subproject.transitive_dependencies || [],
    hasDocker: Boolean(subproject.has_docker),
    containerImages: subproject.container_images || [],
    packageRegistries: subproject.package_registries || [],
    compliance: subproject.company_compliance_percentage || 0,
    ruleResults: subproject.company_rule_results || {},
    isRoot, detected,
  };
}
function projectView(project) {
  const subprojects = project.subprojects.map((subproject) => subprojectView(project, subproject));
  const root = subprojects.find((subproject) => subproject.isRoot) || null;
  const monorepository = subprojects.length > 1;
  const fallback = subprojects.length === 0
    ? subprojectView(project, {
      path: '.', package_manager: project.package_manager, dependencies: [], optional_dependencies: [],
      transitive_dependencies: [],
    }, false)
    : null;
  return {
    project,
    root: root || (monorepository ? null : subprojects[0]) || fallback,
    children: monorepository ? subprojects.filter((subproject) => !subproject.isRoot) : [],
    monorepository,
  };
}

async function showPage() {
  const requestedRoute = window.location.hash.slice(1);
  const routeName = PAGE_ROUTES[requestedRoute] ? requestedRoute : 'dashboard';
  const route = PAGE_ROUTES[routeName];
  document.querySelectorAll('.nav-item, .page').forEach((node) => node.classList.remove('active'));
  document.querySelector(`.nav-item[data-route="${routeName}"]`).classList.add('active');
  document.querySelector(`#${route.page}`).classList.add('active');
  try {
    if (route.source) {
      const sourceChanged = state.dependencySource !== route.source;
      state.dependencySource = route.source;
      if (sourceChanged) state.selectedDependency = null;
      document.querySelector('#catalog-title').textContent = route.title;
      document.querySelector('#dependency-search').placeholder = route.search;
      document.querySelector('#transitive-filter').classList.toggle('control-placeholder', route.source !== 'python');
      if (sourceChanged) {
        document.querySelector('#dependency-detail').replaceChildren(
          element('p', 'empty-state', 'Выберите элемент, чтобы посмотреть версии и проекты.'),
        );
      }
      await loadDependencies();
    } else await ensurePageLoaded(route.page);
  } catch (error) { showError(error); }
}
async function ensurePageLoaded(pageName) {
  if (state.loaded[pageName]) return;
  if (!state.loading[pageName]) {
    const loaders = {
      dashboard: loadDashboard, projects: loadProjects, dependencies: loadDependencies,
      requirements: loadRequirementsPage, parameters: loadParametersPage, admin: loadAdmin,
    };
    state.loading[pageName] = loaders[pageName]().finally(() => { delete state.loading[pageName]; });
  }
  await state.loading[pageName];
}

function projectMatchesFilters(project) {
  const query = document.querySelector('#project-search').value.trim().toLowerCase();
  const rules = [...document.querySelectorAll('.rule-switches input:checked')]
    .map((input) => input.dataset.rule);
  const pythonVersions = project.subprojects
    .map((item) => normalizePythonVersion(item.python_version || item.python_constraint))
    .filter(Boolean)
    .map((version) => `Python ${version}`)
    .join(' ');
  const searchable = `${project.name} ${project.path_with_namespace} ${project.subprojects.map((item) => item.path).join(' ')} ${pythonVersions}`.toLowerCase();
  return (!query || searchable.includes(query))
    && rules.every((rule) => project.company_rule_results?.[rule] === false);
}
function renderProjects() {
  const projects = state.projects.filter(projectMatchesFilters);
  const list = document.querySelector('#project-list');
  list.replaceChildren();
  if (!projects.length) {
    list.append(element('p', 'empty-state', state.projects.length ? 'Проекты не найдены.' : 'Список проектов пуст. Запустите сканирование.'));
    return;
  }
  projects.forEach((project) => {
    const view = projectView(project);
    const selectedProject = project.id === state.selectedId;
    const tree = element('div', 'project-tree');
    const row = element('button');
    row.className = `project-row${selectedProject && state.selectedSubprojectPath === (view.root?.path || null) ? ' active' : ''}`;
    row.type = 'button';
    const identity = element('span');
    identity.append(element('strong', '', project.name), element('small', '', projectPathParts(project.path_with_namespace).join(' › ')));
    if (view.monorepository) {
      identity.append(element('small', 'subproject-summary', `Монорепозиторий · подпроектов: ${view.children.length + (view.root ? 1 : 0)}`));
    }
    row.append(identity, element('time', '', formatDate(project.last_activity_at)));
    row.addEventListener('click', () => selectProject(view, view.root, row));
    tree.append(row);
    if (view.children.length) {
      const children = element('div', 'project-children');
      view.children.forEach((subproject) => {
        const child = element('button');
        child.className = `project-child${selectedProject && state.selectedSubprojectPath === subproject.path ? ' active' : ''}`;
        child.type = 'button';
        child.append(element('span', '', projectPathParts(subproject.path).join(' › ')), packageManagerBadge(subproject.packageManager));
        child.addEventListener('click', () => selectProject(view, subproject, child));
        children.append(child);
      });
      tree.append(children);
    }
    list.append(tree);
  });
}
function appendDetail(container, label, value) {
  container.append(element('p', 'detail-label', label));
  const content = value instanceof Node ? value : element('p', 'detail-value', value || '—');
  container.append(content);
  return content;
}
function appendProjectPath(container, value) {
  const breadcrumb = element('div', 'project-path');
  projectPathParts(value).forEach((part) => breadcrumb.append(element('span', '', part)));
  appendDetail(container, 'Полный путь', breadcrumb);
}
function packageManagerBadge(value) {
  const badge = element('span', 'status-badge', value || '—');
  badge.classList.add(value === 'uv' ? 'manager-uv' : value === 'pip' ? 'manager-pip' : 'manager-other');
  return badge;
}
function dependencyBadge(dependency, onClick = null) {
  const badge = element(onClick ? 'button' : 'span', `dependency-badge${onClick ? ' dependency-badge-link' : ''}`);
  if (onClick) {
    badge.type = 'button';
    badge.addEventListener('click', onClick);
  }
  badge.append(element('strong', '', dependency.name));
  if (dependency.version) badge.append(element('span', '', dependency.version));
  return badge;
}
function dependencyGroup(title, dependencies) {
  const group = element('section', 'dependency-group');
  group.append(element('h4', '', title));
  const items = element('div', 'dependency-badges');
  dependencies.forEach((dependency) => items.append(dependencyBadge(dependency, () => openDependency(dependency.name, 'python'))));
  group.append(items);
  return group;
}
function appendProjectDependencies(container, subproject) {
  const groups = [];
  if (subproject.dependencies.length) groups.push(dependencyGroup('Основные', subproject.dependencies));
  subproject.optionalDependencies.forEach((group) => {
    if (group.dependencies.length) groups.push(dependencyGroup(`Опциональные · ${group.name}`, group.dependencies));
  });
  const content = element('div', 'project-dependencies');
  if (groups.length) content.append(...groups);
  else content.append(element('p', 'empty-state', 'Основные и опциональные зависимости не найдены.'));
  if (subproject.transitiveDependencies.length) {
    const transitive = dependencyGroup('Транзитивные', subproject.transitiveDependencies);
    transitive.hidden = true;
    const button = element('button', 'transitive-toggle', `Показать транзитивные · ${subproject.transitiveDependencies.length}`);
    button.type = 'button';
    button.addEventListener('click', () => {
      transitive.hidden = !transitive.hidden;
      button.textContent = transitive.hidden
        ? `Показать транзитивные · ${subproject.transitiveDependencies.length}`
        : 'Скрыть транзитивные';
    });
    content.append(button, transitive);
  }
  const count = new Set([
    ...subproject.dependencies.map((dependency) => dependency.name),
    ...subproject.optionalDependencies.flatMap((group) => group.dependencies.map((dependency) => dependency.name)),
    ...subproject.transitiveDependencies.map((dependency) => dependency.name),
  ]).size;
  const disclosure = element('details', 'dependency-disclosure');
  disclosure.append(element('summary', '', `Зависимости · ${count}`), content);
  container.append(disclosure);
}
function appendGitLabComponents(container, project) {
  if (!project.gitlab_ci_components?.length) return;
  const componentsByRegistry = new Map();
  project.gitlab_ci_components.forEach((component) => {
    const registry = registryName(component.name);
    if (!componentsByRegistry.has(registry)) componentsByRegistry.set(registry, []);
    componentsByRegistry.get(registry).push(component);
  });
  const registryList = element('div', 'image-registry-list');
  [...componentsByRegistry.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .forEach(([registry, components]) => {
      const group = element('section', 'image-registry-group');
      const badges = element('div', 'dependency-badges');
      components.forEach((component) => badges.append(dependencyBadge(
        { ...component, name: projectPathParts(component.name).slice(-3).join('/') || component.name },
        () => openDependency(component.name, 'ci'),
      )));
      group.append(element('h4', '', registry), badges);
      registryList.append(group);
    });
  appendDetail(container, 'Компоненты GitLab CI по registry', registryList);
}
function appendContainerImages(container, project) {
  if (!project.container_images?.length) return;
  const imagesByRegistry = new Map();
  project.container_images.forEach((image) => {
    if (!imagesByRegistry.has(image.registry)) imagesByRegistry.set(image.registry, []);
    imagesByRegistry.get(image.registry).push(image);
  });
  const registryList = element('div', 'image-registry-list');
  [...imagesByRegistry.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .forEach(([registry, images]) => {
      const group = element('section', 'image-registry-group');
      const badges = element('div', 'dependency-badges');
      images.forEach((image) => badges.append(dependencyBadge(
        { name: image.image, version: image.version },
        () => openDependency(`${image.registry}/${image.image}`, 'docker'),
      )));
      group.append(element('h4', '', registry), badges);
      registryList.append(group);
  });
  appendDetail(container, 'Образы Docker по registry', registryList);
}
function appendProjectHooks(container, project) {
  if (!project.webhooks_accessible) return;
  if (!project.webhooks?.length) {
    appendDetail(container, 'Webhooks', 'Не настроены');
    return;
  }
  const hooks = element('div', 'webhook-list');
  project.webhooks.forEach((hook) => {
    const entry = element('button', 'webhook-entry');
    entry.type = 'button';
    entry.append(element('strong', '', hook.name || hook.url));
    if (hook.name) entry.append(element('small', '', hook.url));
    entry.append(element(
      'small',
      '',
      hook.events.map((event) => HOOK_EVENT_TITLES[event] || event).join(', ') || 'События не выбраны',
    ));
    entry.addEventListener('click', () => openDependency(hook.url, 'webhook'));
    hooks.append(entry);
  });
  appendDetail(container, 'Webhooks', hooks);
}
function normalizedPythonVersion(...values) {
  for (const value of values) {
    const match = value?.match(/(^|\D)(\d+)\.(\d+)/);
    if (match) return `${match[2]}.${match[3]}`;
  }
  return null;
}
function appendTechnologyStatuses(container, project) {
  const statuses = element('div', 'technology-statuses');
  [['Docker', project.has_docker], ['GitLab CI', project.has_gitlab_ci]].forEach(([title, enabled]) => {
    const status = element('span', `technology-status ${enabled ? 'enabled' : 'disabled'}`);
    status.append(element('b', '', enabled ? '✓' : '×'), element('span', '', title));
    statuses.append(status);
  });
  appendDetail(container, 'Технологии', statuses);
}
function appendRuleViolations(container, results) {
  const violations = activeRequirements()
    .filter((requirement) => results?.[requirement.code] === false)
    .map((requirement) => requirement.title);
  if (!violations.length) return;
  const badges = element('div', 'rule-violations');
  violations.forEach((title) => badges.append(element('span', '', title)));
  appendDetail(container, 'Не выполнены правила', badges);
}
function renderProjectDetail(view, subproject) {
  const { project } = view;
  const detail = document.querySelector('#project-detail');
  detail.replaceChildren();
  if (!subproject) {
    detail.append(element('h3', '', project.name), element('p', 'empty-state', 'Выберите подпроект. Корень репозитория не содержит отдельного проекта.'));
    appendProjectPath(detail, project.path_with_namespace);
    appendDetail(detail, 'Основная ветка', project.default_branch);
    appendTechnologyStatuses(detail, project);
    appendRuleViolations(detail, project.company_rule_results);
    appendGitLabComponents(detail, project);
    appendContainerImages(detail, project);
    appendProjectHooks(detail, project);
    return;
  }
  detail.append(element('h3', '', subproject.title));
  appendDetail(detail, 'ID', String(project.id));
  appendProjectPath(detail, subproject.fullPath);
  appendDetail(detail, 'Основная ветка', project.default_branch);
  appendDetail(detail, 'Пакетный менеджер', packageManagerBadge(subproject.packageManager));
  const normalizedPython = normalizedPythonVersion(subproject.pythonVersion, subproject.pythonConstraint);
  const pythonDetails = [
    normalizedPython ? `Python ${normalizedPython}` : 'Не определена',
    subproject.pythonConstraint,
  ].filter(Boolean).join(' · ');
  appendDetail(detail, 'Python', pythonDetails);
  const compliance = element('p', 'detail-value compliance-value', `${subproject.compliance}%`);
  const [dangerThreshold, successThreshold] = parameterRange('project_compliance_thresholds');
  compliance.classList.add(
    subproject.compliance < dangerThreshold
      ? 'compliance-danger'
      : subproject.compliance < successThreshold
        ? 'compliance-warning'
        : 'compliance-success',
  );
  appendDetail(detail, 'Соответствие правилам компании', compliance);
  appendTechnologyStatuses(detail, project);
  appendRuleViolations(detail, subproject.ruleResults);
  appendProjectDependencies(detail, subproject);
  appendGitLabComponents(detail, project);
  appendContainerImages(detail, project);
  appendProjectHooks(detail, project);
  if (project.scan_error) appendDetail(detail, 'Ошибка анализа', project.scan_error);
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
  document.querySelectorAll('.project-row.active, .project-child.active').forEach((node) => node.classList.remove('active'));
  row.classList.add('active');
  renderProjectDetail(view, subproject);
}

function compactStatRow(label, value) {
  const row = element('div');
  row.append(element('span', '', label), element('b', '', String(value)));
  return row;
}
function pythonVersionLink(item) {
  const row = element('button', 'compact-stat-link');
  row.type = 'button';
  const oldestCurrent = parameterValue('python_oldest_current_version');
  const comparison = compareVersions(item.version, oldestCurrent);
  if (comparison < 0) row.classList.add('python-version-danger');
  else if (comparison === 0) row.classList.add('python-version-warning');
  row.append(element('span', '', `Python ${item.version}`), element('b', '', String(item.projects_count)));
  row.addEventListener('click', () => openPythonVersion(item.version));
  return row;
}
function parameterValue(key) {
  return state.parameters.find((parameter) => parameter.key === key).value;
}
function parameterRange(key) {
  return parameterValue(key).split(',').map(Number);
}
function compareVersions(left, right) {
  const leftParts = left.split('.').map(Number);
  const rightParts = right.split('.').map(Number);
  return (leftParts[0] || 0) - (rightParts[0] || 0) || (leftParts[1] || 0) - (rightParts[1] || 0);
}
function stableFraction(value) {
  let hash = 2166136261;
  for (const character of value) {
    hash ^= character.codePointAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0) / 4294967295;
}
function renderTechnologyTarget(target, projectsCount) {
  const definitions = [
    ['Python', target.python_versions], ['Зависимости', target.dependencies],
    ['Образы', target.images], ['Registry', target.registries],
  ];
  const markers = document.querySelector('#target-markers');
  const scaleMaximum = Math.max(Math.ceil(projectsCount * 1.1), 1);
  const markerNodes = definitions.flatMap(([category, sourceItems], categoryIndex) => {
    const items = sourceItems.filter((item) => state.showSingleTechnologies || item.projects_count > 1);
    const topItems = new Set(
      [...items]
        .sort((left, right) => right.projects_count - left.projects_count || left.name.localeCompare(right.name))
        .slice(0, 5),
    );
    return items.map((item) => {
      const marker = element('span', `target-marker target-category-${categoryIndex}`);
      const randomAngle = stableFraction(`${category}:${item.name}:angle`);
      const angle = (-85 + categoryIndex * 90 + randomAngle * 80) * Math.PI / 180;
      const radius = 4 + (1 - Math.min(item.projects_count / scaleMaximum, 1)) * 42;
      marker.style.left = `${50 + Math.cos(angle) * radius}%`;
      marker.style.top = `${50 + Math.sin(angle) * radius}%`;
      const tooltip = `${category} · ${item.name} · ${item.projects_count} проектов`;
      marker.dataset.tooltip = tooltip;
      marker.setAttribute('aria-label', tooltip);
      marker.tabIndex = 0;
      marker.append(element('i'));
      if (topItems.has(item)) {
        marker.classList.add('target-marker-labeled');
        marker.append(element('small', '', item.name));
      }
      return marker;
    });
  });
  markers.replaceChildren(...markerNodes);
}
function renderDashboard(dashboard) {
  document.querySelector('#project-count').textContent = dashboard.projects_count;
  document.querySelector('#subproject-count').textContent = dashboard.subprojects_count;
  document.querySelector('#dependency-count').textContent = dashboard.dependency_counts.total;
  document.querySelector('#direct-dependency-count').textContent = dashboard.dependency_counts.direct;
  document.querySelector('#optional-dependency-count').textContent = dashboard.dependency_counts.optional;
  document.querySelector('#transitive-dependency-count').textContent = dashboard.dependency_counts.transitive;
  document.querySelector('#docker-project-count').textContent = dashboard.docker_projects_count;
  document.querySelector('#gitlab-ci-project-count').textContent = dashboard.gitlab_ci_projects_count;
  document.querySelector('#fastapi-project-count').textContent = dashboard.fastapi_projects_count;
  document.querySelector('#django-project-count').textContent = dashboard.django_projects_count;
  const total = dashboard.projects_count || 1;
  document.querySelector('#docker-project-percentage').textContent = `${Math.round(dashboard.docker_projects_count / total * 100)}% проектов`;
  document.querySelector('#gitlab-ci-project-percentage').textContent = `${Math.round(dashboard.gitlab_ci_projects_count / total * 100)}% проектов`;
  document.querySelector('#fastapi-project-percentage').textContent = `${Math.round(dashboard.fastapi_projects_count / total * 100)}% проектов`;
  document.querySelector('#django-project-percentage').textContent = `${Math.round(dashboard.django_projects_count / total * 100)}% проектов`;
  state.technologyTarget = dashboard.technology_target;
  state.projectsCount = dashboard.projects_count;
  renderTechnologyTarget(dashboard.technology_target, dashboard.projects_count);
  const registries = document.querySelector('#registry-stats');
  registries.replaceChildren(...dashboard.registries.slice(0, 8).map((item) => compactStatRow(item.name, item.projects_count)));
  if (!dashboard.registries.length) registries.append(element('p', 'empty-state', 'Registry не обнаружены.'));

  const pythonVersions = document.querySelector('#python-version-stats');
  pythonVersions.replaceChildren(...dashboard.python_versions.map(pythonVersionLink));
  if (!dashboard.python_versions.length) pythonVersions.append(element('p', 'empty-state', 'Версии не определены.'));

  const statistics = document.querySelector('#package-manager-stats');
  statistics.replaceChildren();
  dashboard.package_managers.filter((item) => item.projects_count > 0).forEach((item) => {
    const row = element('div', 'statistics-row');
    const label = element('div', 'statistics-label');
    label.append(element('strong', '', item.title), element('span', '', `${item.percentage}%`));
    const track = element('div', 'statistics-track');
    const trackValue = element('span');
    trackValue.style.width = `${item.percentage}%`;
    track.append(trackValue);
    row.append(label, track, element('b', '', String(item.projects_count)));
    row.title = `${item.projects_count} репозиториев, ${item.subprojects_count} подпроектов`;
    statistics.append(row);
  });

  const topDependencies = document.querySelector('#top-dependencies');
  topDependencies.replaceChildren();
  dashboard.top_dependencies.forEach((item, index) => {
    const row = element('button', 'dependency-top-row');
    row.type = 'button';
    row.append(element('span', 'dependency-rank', String(index + 1).padStart(2, '0')), element('strong', '', item.name), element('b', '', item.projects_count));
    row.addEventListener('click', () => openDependency(item.name));
    topDependencies.append(row);
  });
  if (!dashboard.top_dependencies.length) topDependencies.append(element('p', 'empty-state', 'Зависимости еще не найдены.'));

  const requirements = document.querySelector('#company-requirements');
  requirements.replaceChildren();
  const configuredByCode = new Map(activeRequirements().map((item) => [item.code, item]));
  const groups = new Map(state.requirementGroups.map((group) => [group.name, []]));
  dashboard.company_requirements.forEach((item) => {
    const configured = configuredByCode.get(item.code);
    const groupName = state.requirementGroups.find((group) => group.id === configured?.group_id)?.name || 'Без группы';
    if (!groups.has(groupName)) groups.set(groupName, []);
    groups.get(groupName).push(item);
  });
  groups.forEach((itemsForGroup, groupName) => {
    if (!itemsForGroup.length) return;
    const group = element('section', 'requirement-group');
    const items = element('div', 'requirement-group-items');
    itemsForGroup.forEach((item) => {
      const card = element('button', 'requirement');
      card.type = 'button';
      const progress = element('div', 'requirement-progress');
      const progressValue = element('span');
      progressValue.style.width = `${item.compliance_percentage}%`;
      progress.append(progressValue);
      card.append(
        element('strong', '', item.title),
        element('b', '', `${item.compliance_percentage}%`),
        progress,
        element('small', '', `${item.matching_projects} из ${item.total_projects}`),
      );
      card.title = item.description;
      card.addEventListener('click', () => openRuleViolations(item.code));
      items.append(card);
    });
    group.append(element('h4', '', groupName), items);
    requirements.append(group);
  });

  const quality = dashboard.data_quality;
  renderDataQuality(quality);
  renderLastScan(dashboard.last_scan);
}
function renderDataQuality(quality) {
  document.querySelector('#data-quality-stats').replaceChildren(
    compactStatRow('Менеджер не определен', quality.unknown_package_manager),
    compactStatRow('Версия Python не определена', quality.unknown_python_version),
    compactStatRow('Без подпроектов', quality.projects_without_subprojects),
    compactStatRow('Ошибки анализа', quality.analysis_errors),
  );
}
function renderLastScan(scan) {
  const lastScan = document.querySelector('#last-scan-stats');
  lastScan.replaceChildren();
  if (scan) {
    lastScan.append(
      compactStatRow('Завершено', formatDate(scan.completed_at)),
      compactStatRow('Длительность', formatDuration(scan.duration_seconds)),
      compactStatRow('Повторно использовано', scan.reused_projects),
      compactStatRow('Пропущено', scan.skipped_projects),
      compactStatRow('Ошибки', scan.errors_count),
      compactStatRow('Обращения к GitLab', scan.gitlab_requests),
    );
  } else lastScan.append(element('p', 'empty-state', 'Сканирование еще не запускалось.'));
}
function optionSelect(options, value, className) {
  const select = element('select', className);
  options.forEach((option) => {
    const node = element('option', '', option.title);
    node.value = option.value;
    node.selected = option.value === value;
    select.append(node);
  });
  return select;
}
function conditionLogicSelect(value = 'and') {
  return optionSelect(
    [
      { value: 'and', title: 'И — должны выполняться все' },
      { value: 'or', title: 'ИЛИ — достаточно одного' },
    ],
    value,
    'condition-group-logic',
  );
}
function addRequirementCondition(condition = {}, container = document.querySelector('#requirement-conditions')) {
  const row = element('div', 'requirement-condition');
  const source = optionSelect(state.requirementCatalog.sources, condition.source, 'condition-source');
  const operator = optionSelect(state.requirementCatalog.operators, condition.operator, 'condition-operator');
  const values = element('input', 'condition-values');
  values.required = true;
  values.placeholder = 'Значения через запятую';
  values.value = (condition.values || []).join(', ');
  const emptyLabel = element('label', 'condition-empty');
  const empty = element('input');
  empty.type = 'checkbox';
  empty.className = 'condition-empty-result';
  empty.checked = Boolean(condition.empty_result);
  emptyLabel.append(empty, document.createTextNode(' Если данных нет — требование выполнено'));
  const remove = element('button', 'condition-remove');
  remove.type = 'button';
  remove.title = 'Удалить условие';
  remove.setAttribute('aria-label', 'Удалить условие');
  remove.append(iconElement('close'));
  remove.addEventListener('click', () => {
    if (container.children.length > 1) row.remove();
  });
  row.append(source, operator, values, emptyLabel, remove);
  container.append(row);
}
function addRequirementConditionGroup(group = {}, container = document.querySelector('#requirement-conditions')) {
  const node = element('section', 'condition-group');
  const heading = element('div', 'condition-group-heading');
  const logic = conditionLogicSelect(group.logic || 'and');
  logic.setAttribute('aria-label', 'Логика группы условий');
  const logicField = element('label', 'condition-group-logic-field');
  logicField.append(document.createTextNode('Как объединять условия'), logic);
  const actions = element('div', 'condition-group-actions');
  const addCondition = iconButton('plus', 'secondary-button', 'Добавить условие в группу');
  const addGroup = iconButton('group', 'secondary-button', 'Добавить вложенную группу');
  const remove = iconButton('trash', 'danger-button', 'Удалить группу условий');
  const items = element('div', 'condition-group-items');
  addCondition.addEventListener('click', () => addRequirementCondition({}, items));
  addGroup.addEventListener('click', () => addRequirementConditionGroup({}, items));
  remove.addEventListener('click', () => {
    if (container.children.length > 1) node.remove();
  });
  actions.append(addCondition, addGroup, remove);
  heading.append(element('strong', '', 'Группа условий'), actions);
  node.append(heading, logicField, items);
  (group.items || [{}]).forEach((condition) => addRequirementConditionNode(condition, items));
  container.append(node);
}
function addRequirementConditionNode(node, container = document.querySelector('#requirement-conditions')) {
  if (node && Array.isArray(node.items)) addRequirementConditionGroup(node, container);
  else addRequirementCondition(node || {}, container);
}
function conditionNodePayload(node) {
  if (node.classList.contains('condition-group')) {
    const items = node.querySelector(':scope > .condition-group-items');
    return {
      logic: node.querySelector(':scope > .condition-group-logic-field .condition-group-logic').value,
      items: [...items.children].map(conditionNodePayload),
    };
  }
  return {
    source: node.querySelector('.condition-source').value,
    operator: node.querySelector('.condition-operator').value,
    values: node.querySelector('.condition-values').value.split(',').map((value) => value.trim()).filter(Boolean),
    empty_result: node.querySelector('.condition-empty-result').checked,
  };
}
function countConditionNodes(nodes) {
  return nodes.reduce((count, node) => count + (
    Array.isArray(node.items) ? countConditionNodes(node.items) : 1
  ), 0);
}
function requirementPayload() {
  const requirementId = Number(document.querySelector('#requirement-id').value);
  const current = state.requirements.find((requirement) => requirement.id === requirementId);
  return {
    code: document.querySelector('#requirement-code').value.trim(),
    title: document.querySelector('#requirement-title').value.trim(),
    group_id: current?.group_id || state.selectedRequirementGroupId,
    description: document.querySelector('#requirement-description').value.trim(),
    enabled: current?.enabled ?? true,
    sort_order: current?.sort_order || (
      state.requirements.filter((requirement) => requirement.group_id === state.selectedRequirementGroupId).length + 1
    ) * 10,
    condition: {
      logic: document.querySelector('#requirement-condition-logic').value,
      items: [...document.querySelector('#requirement-conditions').children].map(conditionNodePayload),
    },
  };
}
function resetRequirementForm() {
  document.querySelector('#requirement-form').reset();
  document.querySelector('#requirement-id').value = '';
  document.querySelector('#requirement-conditions').replaceChildren();
  addRequirementCondition();
  document.querySelector('#requirement-dialog-title').textContent = 'Новое требование';
}
function editRequirement(requirement) {
  document.querySelector('#requirement-id').value = requirement.id;
  document.querySelector('#requirement-title').value = requirement.title;
  document.querySelector('#requirement-code').value = requirement.code;
  document.querySelector('#requirement-description').value = requirement.description;
  document.querySelector('#requirement-condition-logic').value = requirement.condition.logic;
  document.querySelector('#requirement-conditions').replaceChildren();
  requirement.condition.items.forEach((condition) => addRequirementConditionNode(condition));
  document.querySelector('#requirement-dialog-title').textContent = 'Редактирование требования';
  document.querySelector('#requirement-dialog').showModal();
  document.querySelector('#requirement-title').focus();
}
async function removeRequirement(requirement) {
  const confirmed = await confirmAction(
    'Удалить требование?',
    `Требование «${requirement.title}» будет удалено без возможности восстановления.`,
    'Удалить требование',
  );
  if (!confirmed) return;
  await api(`${API.requirements}${requirement.id}`, { method: 'DELETE' });
  await reloadRequirements();
}
function groupPayload() {
  const groupId = Number(document.querySelector('#requirement-group-id').value);
  const current = state.requirementGroups.find((group) => group.id === groupId);
  return {
    name: document.querySelector('#requirement-group-name').value.trim(),
    description: document.querySelector('#requirement-group-description').value.trim(),
    sort_order: current?.sort_order || (state.requirementGroups.length + 1) * 10,
  };
}
function resetGroupForm() {
  document.querySelector('#requirement-group-form').reset();
  document.querySelector('#requirement-group-id').value = '';
  document.querySelector('#group-dialog-title').textContent = 'Новая группа';
}
function editRequirementGroup(group) {
  document.querySelector('#requirement-group-id').value = group.id;
  document.querySelector('#requirement-group-name').value = group.name;
  document.querySelector('#requirement-group-description').value = group.description;
  document.querySelector('#group-dialog-title').textContent = 'Редактирование группы';
  document.querySelector('#group-dialog').showModal();
  document.querySelector('#requirement-group-name').focus();
}
async function removeRequirementGroup(group) {
  const confirmed = await confirmAction(
    'Удалить группу?',
    `Группа «${group.name}» будет удалена без возможности восстановления.`,
    'Удалить группу',
  );
  if (!confirmed) return;
  await api(`${API.requirementGroups}${group.id}`, { method: 'DELETE' });
  if (state.selectedRequirementGroupId === group.id) state.selectedRequirementGroupId = null;
  await reloadRequirements();
}
function renderRequirementGroups() {
  const container = document.querySelector('#requirement-groups');
  if (!container) return;
  document.querySelector('#requirements-count').textContent = state.requirementGroups.length;
  container.replaceChildren();
  state.requirementGroups.forEach((group) => {
    const node = element(
      'button',
      `requirement-group-list-item${group.id === state.selectedRequirementGroupId ? ' active' : ''}`,
    );
    node.type = 'button';
    node.dataset.groupId = group.id;
    node.title = `Открыть группу «${group.name}»`;
    const handle = element('span', 'group-drag-handle', '⋮⋮');
    handle.draggable = true;
    handle.title = 'Перетащить группу';
    handle.addEventListener('click', (event) => event.stopPropagation());
    const summary = element('div');
    const groupRequirements = state.requirements.filter((requirement) => requirement.group_id === group.id);
    summary.append(
      element('strong', '', group.name),
      element('small', '', `${groupRequirements.length} из 6`),
    );
    node.append(handle, summary, element('span', 'group-open-mark', '›'));
    node.addEventListener('click', () => {
      state.selectedRequirementGroupId = group.id;
      renderRequirementGroups();
    });
    container.append(node);
  });
  if (!state.requirementGroups.length) container.append(element('p', 'empty-state', 'Сначала создайте группу.'));
  renderRequirementGroupDetail();
}
function renderRequirementGroupDetail() {
  const detail = document.querySelector('#requirement-group-detail');
  const group = state.requirementGroups.find((item) => item.id === state.selectedRequirementGroupId);
  detail.replaceChildren();
  delete detail.dataset.groupId;
  if (!group) {
    detail.append(element('p', 'empty-state', 'Выберите группу, чтобы посмотреть требования.'));
    return;
  }
  detail.dataset.groupId = group.id;
  const heading = element('div', 'requirement-detail-heading');
  const identity = element('div');
  identity.append(element('h3', '', group.name));
  if (group.description) identity.append(element('p', 'muted', group.description));
  const groupRequirements = state.requirements.filter((requirement) => requirement.group_id === group.id);
  const actions = element('div', 'admin-requirement-actions');
  const edit = iconButton('edit', 'secondary-button', 'Изменить группу');
  edit.addEventListener('click', () => editRequirementGroup(group));
  const add = iconButton('plus', 'primary-button', 'Добавить требование');
  add.disabled = groupRequirements.length >= 6;
  add.addEventListener('click', () => {
    resetRequirementForm();
    document.querySelector('#requirement-dialog').showModal();
  });
  const remove = iconButton('trash', 'danger-button', 'Удалить группу');
  remove.addEventListener('click', () => removeRequirementGroup(group).catch(showError));
  actions.append(edit, add, remove);
  heading.append(identity, actions);
  const requirements = element('div', 'requirement-detail-items');
  groupRequirements.forEach((requirement) => requirements.append(requirementTreeItem(requirement)));
  if (!groupRequirements.length) requirements.append(element('p', 'empty-state', 'В группе пока нет требований.'));
  detail.append(heading, requirements);
}
function requirementTreeItem(requirement) {
  const item = element('div', `requirement-tree-item${requirement.enabled ? '' : ' disabled'}`);
  item.dataset.requirementId = requirement.id;
  const handle = element('span', 'requirement-drag-handle', '⋮⋮');
  handle.draggable = true;
  handle.title = 'Перетащить требование';
  const summary = element('div', 'requirement-tree-summary');
  summary.append(
    element('strong', '', requirement.title),
    element('small', '', `${requirement.code} · условий: ${countConditionNodes(requirement.condition.items)}`),
  );
  const enabled = element('label', 'switch requirement-enabled-switch');
  const input = element('input');
  input.type = 'checkbox';
  input.checked = requirement.enabled;
  input.addEventListener('change', async () => {
    try { await setRequirementEnabled(requirement, input.checked); } catch (error) {
      input.checked = requirement.enabled;
      showError(error);
    }
  });
  enabled.append(input, element('span'));
  enabled.title = requirement.enabled ? 'Требование включено' : 'Требование выключено';
  const actions = element('div', 'admin-requirement-actions');
  const edit = iconButton('edit', 'secondary-button', 'Изменить требование');
  edit.addEventListener('click', () => editRequirement(requirement));
  const move = iconButton('move', 'secondary-button', 'Сменить группу');
  move.disabled = !state.requirementGroups.some((group) => (
    group.id !== requirement.group_id
    && state.requirements.filter((item) => item.group_id === group.id).length < 6
  ));
  move.addEventListener('click', () => openRequirementMove(requirement));
  const remove = iconButton('trash', 'danger-button', 'Удалить требование');
  remove.addEventListener('click', () => removeRequirement(requirement).catch(showError));
  actions.append(edit, move, remove);
  item.append(handle, summary, enabled, actions);
  return item;
}
async function setRequirementEnabled(requirement, enabled) {
  const updated = await api(`${API.requirements}${requirement.id}/enabled`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }),
  });
  state.requirements = state.requirements.map((item) => item.id === updated.id ? updated : item);
  state.loaded.dashboard = false;
  state.loaded.projects = false;
  renderRuleFilters();
  renderRequirementGroups();
}
function openRequirementMove(requirement) {
  document.querySelector('#move-requirement-id').value = requirement.id;
  document.querySelector('#move-requirement-title').textContent = requirement.title;
  const select = document.querySelector('#move-requirement-group');
  select.replaceChildren();
  state.requirementGroups
    .filter((group) => (
      group.id !== requirement.group_id
      && state.requirements.filter((item) => item.group_id === group.id).length < 6
    ))
    .forEach((group) => {
      const option = element('option', '', group.name);
      option.value = group.id;
      select.append(option);
    });
  document.querySelector('#move-requirement-dialog').showModal();
}
async function moveRequirement(requirementId, groupId) {
  await api(`${API.requirements}${requirementId}/group`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ group_id: groupId }),
  });
  state.requirements = await api(API.requirements);
  state.loaded.dashboard = false;
  state.loaded.projects = false;
  renderRuleFilters();
  renderRequirementGroups();
}
async function saveRequirementGroupOrder() {
  const groupIds = [...document.querySelectorAll('#requirement-groups [data-group-id]')]
    .map((item) => Number(item.dataset.groupId));
  state.requirementGroups = await api(`${API.requirementGroups}order`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ group_ids: groupIds }),
  });
  state.loaded.dashboard = false;
  renderRequirementGroups();
}
async function saveRequirementOrder(groupNode) {
  const requirementIds = [...groupNode.querySelectorAll('[data-requirement-id]')]
    .map((item) => Number(item.dataset.requirementId));
  state.requirements = await api(`${API.requirements}order`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ group_id: Number(groupNode.dataset.groupId), requirement_ids: requirementIds }),
  });
  state.loaded.dashboard = false;
  renderRequirementGroups();
}
async function reloadRequirements() {
  [state.requirements, state.requirementGroups] = await Promise.all([
    api(API.requirements), api(API.requirementGroups),
  ]);
  if (!state.requirementGroups.some((group) => group.id === state.selectedRequirementGroupId)) {
    state.selectedRequirementGroupId = null;
  }
  state.loaded.dashboard = false;
  state.loaded.projects = false;
  state.loaded.requirements = false;
  renderRuleFilters();
  renderRequirementGroups();
  resetRequirementForm();
  resetGroupForm();
}
async function loadDashboard() {
  const [dashboard] = await Promise.all([api(API.dashboard), ensureRequirements(), ensureParameters()]);
  renderDashboard(dashboard);
  state.loaded.dashboard = true;
}
async function ensureParameters() {
  if (!state.parameters.length) state.parameters = await api(API.parameters);
}
function renderParameters() {
  const fields = document.querySelector('#parameter-fields');
  fields.replaceChildren();
  state.parameters.forEach((parameter) => {
    if (parameter.value_type === 'percentage_range') {
      fields.append(percentageParameterField(parameter));
      return;
    }
    const label = element('label', 'parameter-field');
    const input = element('input');
    input.className = 'parameter-value-input';
    input.name = parameter.key;
    input.value = parameter.value;
    input.required = true;
    if (parameter.value_type === 'version') {
      input.inputMode = 'decimal';
      input.pattern = '\\d+\\.\\d+';
      input.placeholder = '3.11';
    } else if (parameter.value_type === 'integer') {
      input.type = 'number';
      input.step = '1';
      if (parameter.min_value !== null) input.min = parameter.min_value;
      if (parameter.max_value !== null) input.max = parameter.max_value;
    }
    label.append(element('strong', '', parameter.title), input);
    if (parameter.description) label.append(element('small', '', parameter.description));
    fields.append(label);
  });
}
function percentageParameterField(parameter) {
  const field = element('section', 'parameter-field percentage-parameter');
  const hidden = element('input');
  hidden.type = 'hidden';
  hidden.name = parameter.key;
  const minimum = parameter.min_value ?? 0;
  const maximum = parameter.max_value ?? 100;
  let [lowerValue, upperValue] = parameter.value.split(',').map(Number);
  const preview = element('div', 'threshold-preview');
  const danger = element('span', 'threshold-danger');
  const warning = element('span', 'threshold-warning');
  const success = element('span', 'threshold-success');
  preview.append(danger, warning, success);
  const slider = element('div', 'threshold-slider');
  const lower = element('input');
  const upper = element('input');
  [lower, upper].forEach((input) => {
    input.type = 'range';
    input.className = 'threshold-range-input';
    input.min = minimum;
    input.max = maximum;
    input.step = '1';
  });
  lower.setAttribute('aria-label', 'Начало зоны предупреждения');
  upper.setAttribute('aria-label', 'Начало успешной зоны');
  lower.value = lowerValue;
  upper.value = upperValue;
  const lowerOutput = element('output');
  const upperOutput = element('output');
  const values = element('div', 'threshold-values');
  const lowerLabel = element('span', 'threshold-value');
  const upperLabel = element('span', 'threshold-value');
  lowerLabel.append(element('span', '', 'Предупреждение'), lowerOutput);
  upperLabel.append(element('span', '', 'Успешно'), upperOutput);
  values.append(lowerLabel, upperLabel);
  slider.append(preview, lower, upper);
  function update(changed) {
    lowerValue = Number(lower.value);
    upperValue = Number(upper.value);
    if (lowerValue >= upperValue) {
      if (changed === lower) upperValue = Math.min(maximum, lowerValue + 1);
      else lowerValue = Math.max(minimum, upperValue - 1);
      lower.value = lowerValue;
      upper.value = upperValue;
    }
    hidden.value = `${lowerValue},${upperValue}`;
    lowerOutput.value = `${lowerValue}%`;
    upperOutput.value = `${upperValue}%`;
    const span = maximum - minimum || 1;
    danger.style.width = `${(lowerValue - minimum) / span * 100}%`;
    warning.style.width = `${(upperValue - lowerValue) / span * 100}%`;
    success.style.width = `${(maximum - upperValue) / span * 100}%`;
  }
  lower.addEventListener('input', () => update(lower));
  upper.addEventListener('input', () => update(upper));
  update();
  field.append(element('strong', '', parameter.title), slider, values, hidden);
  if (parameter.description) field.append(element('small', '', parameter.description));
  return field;
}
async function loadParametersPage() {
  await ensureParameters();
  renderParameters();
  state.loaded.parameters = true;
}
async function saveParameters() {
  const values = Object.fromEntries(state.parameters.map((parameter) => [
    parameter.key,
    document.querySelector(`#parameters-form [name="${parameter.key}"]`).value.trim(),
  ]));
  state.parameters = await api(API.parameters, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ values }),
  });
  state.loaded.dashboard = false;
  renderParameters();
}
async function loadAdmin() {
  const dashboard = await api(API.dashboard);
  renderLastScan(dashboard.last_scan);
  renderDataQuality(dashboard.data_quality);
  state.loaded.admin = true;
}
async function loadRequirementsPage() {
  await ensureRequirements();
  renderRequirementGroups();
  if (!document.querySelector('.requirement-condition')) addRequirementCondition();
  state.loaded.requirements = true;
}
async function loadProjects() {
  const [projects] = await Promise.all([api(API.projects), ensureRequirements(), ensureParameters()]);
  state.projects = projects;
  state.loaded.projects = true;
  renderProjects();
  const selected = state.projects.find((project) => project.id === state.selectedId);
  if (selected) {
    const view = projectView(selected);
    const entries = [view.root, ...view.children].filter(Boolean);
    const subproject = entries.find((item) => item.path === state.selectedSubprojectPath) || view.root;
    state.selectedSubprojectPath = subproject?.path || null;
    renderProjectDetail(view, subproject);
  }
}

function renderDependencies() {
  const query = document.querySelector('#dependency-search').value.trim().toLowerCase();
  const dependencies = state.dependencies
    .map((dependency) => ({ dependency, visible: visibleDependencyData(dependency) }))
    .filter(({ dependency, visible }) => dependency.name.includes(query) && visible.projectsCount);
  const list = document.querySelector('#dependency-list');
  list.replaceChildren();
  if (!dependencies.length) {
    list.append(element('p', 'empty-state', state.dependencies.length ? 'Элементы не найдены.' : 'Список пуст.'));
    return;
  }
  dependencies.forEach(({ dependency, visible }) => {
    const row = element('button');
    row.type = 'button';
    row.className = `dependency-row${dependency.name === state.selectedDependency ? ' active' : ''}`;
    const identity = element('span');
    const levels = visible.levels.map((level) => LEVEL_TITLES[level]).join(', ');
    const metadata = state.dependencySource === 'python'
      ? `${levels} · вариантов версий: ${visible.versions.length}`
      : `вариантов версий: ${visible.versions.length}`;
    identity.append(element('strong', '', dependency.name), element('small', '', metadata));
    row.append(identity, element('b', '', visible.projectsCount));
    row.addEventListener('click', () => selectDependency(dependency, row));
    list.append(row);
  });
}
function visibleDependencyData(dependency) {
  const versions = dependency.versions
    .map((version) => ({
      ...version,
      projects: version.projects.filter((project) => (
        state.dependencySource !== 'python' || state.showTransitive || project.level !== 'transitive'
      )),
    }))
    .filter((version) => version.projects.length);
  const projects = versions.flatMap((version) => version.projects);
  const levels = [...new Set(projects.map((project) => project.level))];
  return {
    versions,
    levels: dependency.levels.filter((level) => levels.includes(level)),
    projectsCount: new Set(projects.map((project) => project.id)).size,
  };
}
function renderDependencyDetail(dependency) {
  const detail = document.querySelector('#dependency-detail');
  detail.replaceChildren();
  const visible = visibleDependencyData(dependency);
  detail.append(element('h3', '', dependency.name));
  if (state.dependencySource === 'python') appendDetail(detail, 'Типы использования', visible.levels.map((level) => LEVEL_TITLES[level]).join(', '));
  appendDetail(detail, 'Используется в проектах', String(visible.projectsCount));
  const versions = element('div', 'dependency-versions');
  visible.versions.forEach((version) => {
    const group = element('section', 'dependency-version');
    group.append(element('h4', '', version.version || 'Версия не указана'));
    const projects = element('div', 'dependency-projects');
    version.projects.forEach((project) => {
      const link = element('a', 'dependency-project');
      link.href = project.web_url;
      link.target = '_blank';
      link.rel = 'noreferrer';
      link.append(
        element('strong', '', project.path_with_namespace),
        element('small', '', `${project.subproject_path === '.' ? 'Корень репозитория' : project.subproject_path}${state.dependencySource === 'python' ? ` · ${LEVEL_TITLES[project.level]}` : ''}`),
      );
      projects.append(link);
    });
    group.append(projects);
    versions.append(group);
  });
  detail.append(versions);
}
function selectDependency(dependency, row) {
  state.selectedDependency = dependency.name;
  document.querySelector('.dependency-row.active')?.classList.remove('active');
  row.classList.add('active');
  renderDependencyDetail(dependency);
}
async function loadDependencies() {
  if (!state.dependencyCache[state.dependencySource]) {
    state.dependencyCache[state.dependencySource] = await api(`${API.dependencies}?source=${state.dependencySource}`);
  }
  state.dependencies = state.dependencyCache[state.dependencySource];
  state.loaded.dependencies = true;
  renderDependencies();
  const selected = state.dependencies.find((dependency) => dependency.name === state.selectedDependency);
  if (selected) renderDependencyDetail(selected);
}
async function openDependency(name, source = 'python') {
  state.dependencySource = source;
  document.querySelector('#transitive-filter').classList.toggle('control-placeholder', source !== 'python');
  state.selectedDependency = name;
  window.location.hash = SOURCE_ROUTES[source];
  await loadDependencies();
  const dependency = state.dependencies.find((item) => item.name === name);
  if (dependency) renderDependencyDetail(dependency);
}
async function openRuleViolations(code) {
  document.querySelectorAll('.rule-switches input').forEach((input) => {
    input.checked = input.dataset.rule === code;
  });
  window.location.hash = 'projects';
  await ensurePageLoaded('projects');
  renderProjects();
}
async function openPythonVersion(version) {
  document.querySelectorAll('.rule-switches input').forEach((input) => { input.checked = false; });
  document.querySelector('#project-search').value = `Python ${version}`;
  window.location.hash = 'projects';
  await ensurePageLoaded('projects');
  renderProjects();
}

function renderScanStatus(scan) {
  document.querySelector('#scan-state').textContent = scan.state_title;
  document.querySelector('#scan-button').disabled = scan.state === 'running';
  document.querySelector('#scan-dot').className = scan.state;
  let description = 'Сканирование еще не запускалось.';
  if (scan.state === 'running') description = `${PHASE_TITLES[scan.phase]} · запущено ${formatDate(scan.started_at)}`;
  if (scan.state === 'completed') description = `Завершено ${formatDate(scan.completed_at)} · проектов: ${scan.projects_count}`;
  if (scan.state === 'failed') description = `Завершено ${formatDate(scan.completed_at)} · ${scan.error || 'неизвестная ошибка'}`;
  document.querySelector('#scan-description').textContent = description;
  document.querySelector('#scan-progress-value').style.width = `${scan.progress_percentage}%`;
  document.querySelector('#scan-progress-label').textContent = `${scan.completed_steps} из ${scan.total_steps} этапов · собрано ${scan.collected_projects}, проанализировано ${scan.analyzed_projects}, повторно ${scan.reused_projects}`;
  document.querySelector('#scan-duration').textContent = formatDuration(scan.duration_seconds);
  document.querySelector('#scan-requests').textContent = `Обращений к GitLab: ${scan.gitlab_requests}`;
  document.querySelector('#scan-current-project').textContent = scan.current_project ? `Сейчас: ${scan.current_project}` : '';
  const errors = document.querySelector('#scan-errors');
  const errorList = document.querySelector('#scan-errors-list');
  const allErrors = [...scan.errors];
  if (scan.error && !allErrors.includes(scan.error)) allErrors.push(scan.error);
  errors.hidden = allErrors.length === 0;
  document.querySelector('#scan-errors-count').textContent = allErrors.length;
  errorList.replaceChildren(...allErrors.map((error) => element('p', '', error)));
}
function connectScanStatusSocket() {
  const socketProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  window.clearTimeout(state.scanReconnectTimer);
  if (state.scanSocket?.readyState === WebSocket.OPEN || state.scanSocket?.readyState === WebSocket.CONNECTING) return;
  const socket = new WebSocket(`${socketProtocol}//${window.location.host}/api/scan/ws`);
  state.scanSocket = socket;
  socket.addEventListener('message', (event) => {
    handleScanStatus(JSON.parse(event.data)).catch(showError);
  });
  socket.addEventListener('close', () => {
    if (state.scanSocket === socket) state.scanSocket = null;
    state.scanReconnectTimer = window.setTimeout(connectScanStatusSocket, 3000);
  });
  socket.addEventListener('error', () => socket.close());
}
async function handleScanStatus(scan) {
  const previousState = state.scanState;
  state.scanState = scan.state;
  state.scanStatus = scan;
  renderScanStatus(scan);
  if (previousState === 'running' && scan.state === 'completed') {
    state.dependencyCache = {};
    const reloads = [loadDashboard()];
    if (state.loaded.projects) reloads.push(loadProjects());
    if (state.loaded.dependencies) reloads.push(loadDependencies());
    await Promise.all(reloads);
  }
}
function updateScanDuration() {
  const scan = state.scanStatus;
  if (scan?.state !== 'running' || !scan.started_at) return;
  const seconds = Math.max(0, (Date.now() - new Date(scan.started_at).getTime()) / 1000);
  document.querySelector('#scan-duration').textContent = formatDuration(seconds);
}
function showError(error) {
  const toast = document.querySelector('#global-error');
  toast.textContent = error.message;
  toast.hidden = false;
  window.setTimeout(() => { toast.hidden = true; }, 5000);
}

document.querySelectorAll('.nav-item').forEach((item) => {
  item.addEventListener('click', () => { window.location.hash = item.dataset.route; });
});
window.addEventListener('hashchange', showPage);
document.querySelector('#project-search').addEventListener('input', renderProjects);
document.querySelector('#dependency-search').addEventListener('input', renderDependencies);
document.querySelector('#show-transitive').addEventListener('change', (event) => {
  state.showTransitive = event.target.checked;
  renderDependencies();
  const selected = state.dependencies.find((dependency) => dependency.name === state.selectedDependency);
  if (selected) renderDependencyDetail(selected);
});
document.querySelector('#target-show-single').addEventListener('change', (event) => {
  state.showSingleTechnologies = event.target.checked;
  if (state.technologyTarget) renderTechnologyTarget(state.technologyTarget, state.projectsCount);
});
const themeToggle = document.querySelector('#theme-toggle');
themeToggle.checked = document.documentElement.dataset.theme === 'dark';
themeToggle.addEventListener('change', () => {
  const theme = themeToggle.checked ? 'dark' : 'light';
  document.documentElement.dataset.theme = theme;
  try { localStorage.setItem('radar-theme', theme); } catch (error) { /* Тема сохранится до перезагрузки. */ }
});
document.querySelector('#scan-button').addEventListener('click', async () => {
  try {
    const scan = await api(API.scan, { method: 'POST' });
    await handleScanStatus(scan);
  } catch (error) { showError(error); }
});
document.querySelector('#parameters-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  try { await saveParameters(); } catch (error) { showError(error); }
});
document.querySelector('#add-condition').addEventListener('click', () => addRequirementCondition());
document.querySelector('#add-condition-group').addEventListener('click', () => addRequirementConditionGroup());
document.querySelector('#create-group').addEventListener('click', () => {
  resetGroupForm();
  document.querySelector('#group-dialog').showModal();
});
document.querySelector('#cancel-requirement-edit').addEventListener('click', () => {
  document.querySelector('#requirement-dialog').close();
  resetRequirementForm();
});
document.querySelector('#cancel-group-edit').addEventListener('click', () => {
  document.querySelector('#group-dialog').close();
  resetGroupForm();
});
document.querySelector('#cancel-requirement-move').addEventListener('click', () => {
  document.querySelector('#move-requirement-dialog').close();
});
const requirementGroups = document.querySelector('#requirement-groups');
let draggedGroup = null;
requirementGroups.addEventListener('dragstart', (event) => {
  if (!event.target.closest('.group-drag-handle')) return;
  draggedGroup = event.target.closest('[data-group-id]');
  draggedGroup.classList.add('group-dragging');
  event.dataTransfer.effectAllowed = 'move';
  event.dataTransfer.setData('text/plain', draggedGroup.dataset.groupId);
});
requirementGroups.addEventListener('dragover', (event) => {
  if (!draggedGroup) return;
  event.preventDefault();
  const target = event.target.closest('[data-group-id]');
  if (!target || target === draggedGroup) return;
  const bounds = target.getBoundingClientRect();
  const afterTarget = event.clientY > bounds.top + bounds.height / 2;
  requirementGroups.insertBefore(draggedGroup, afterTarget ? target.nextSibling : target);
});
requirementGroups.addEventListener('drop', async (event) => {
  if (!draggedGroup) return;
  event.preventDefault();
  try { await saveRequirementGroupOrder(); } catch (error) {
    showError(error);
    await reloadRequirements();
  }
});
requirementGroups.addEventListener('dragend', () => {
  draggedGroup?.classList.remove('group-dragging');
  draggedGroup = null;
});
let draggedRequirement = null;
const requirementGroupDetail = document.querySelector('#requirement-group-detail');
requirementGroupDetail.addEventListener('dragstart', (event) => {
  if (!event.target.closest('.requirement-drag-handle')) return;
  draggedRequirement = event.target.closest('[data-requirement-id]');
  draggedRequirement.classList.add('requirement-dragging');
  event.dataTransfer.effectAllowed = 'move';
  event.dataTransfer.setData('text/plain', draggedRequirement.dataset.requirementId);
});
requirementGroupDetail.addEventListener('dragover', (event) => {
  if (!draggedRequirement) return;
  event.preventDefault();
  const target = event.target.closest('[data-requirement-id]');
  if (!target || target === draggedRequirement) return;
  const sourceGroup = draggedRequirement.closest('[data-group-id]');
  if (target.closest('[data-group-id]') !== sourceGroup) return;
  const bounds = target.getBoundingClientRect();
  const afterTarget = event.clientY > bounds.top + bounds.height / 2;
  target.parentElement.insertBefore(draggedRequirement, afterTarget ? target.nextSibling : target);
});
requirementGroupDetail.addEventListener('drop', async (event) => {
  if (!draggedRequirement) return;
  event.preventDefault();
  const groupNode = draggedRequirement.closest('[data-group-id]');
  try { await saveRequirementOrder(groupNode); } catch (error) {
    showError(error);
    await reloadRequirements();
  }
});
requirementGroupDetail.addEventListener('dragend', () => {
  draggedRequirement?.classList.remove('requirement-dragging');
  draggedRequirement = null;
});
document.querySelector('#requirement-group-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const groupId = document.querySelector('#requirement-group-id').value;
  try {
    await api(groupId ? `${API.requirementGroups}${groupId}` : API.requirementGroups, {
      method: groupId ? 'PUT' : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(groupPayload()),
    });
    await reloadRequirements();
    document.querySelector('#group-dialog').close();
  } catch (error) { showError(error); }
});
document.querySelector('#move-requirement-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  try {
    await moveRequirement(
      Number(document.querySelector('#move-requirement-id').value),
      Number(document.querySelector('#move-requirement-group').value),
    );
    document.querySelector('#move-requirement-dialog').close();
  } catch (error) { showError(error); }
});
document.querySelector('#requirement-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const requirementId = document.querySelector('#requirement-id').value;
  try {
    await api(requirementId ? `${API.requirements}${requirementId}` : API.requirements, {
      method: requirementId ? 'PUT' : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requirementPayload()),
    });
    await reloadRequirements();
    document.querySelector('#requirement-dialog').close();
  } catch (error) { showError(error); }
});
showPage();
connectScanStatusSocket();
window.setInterval(updateScanDuration, 1000);
