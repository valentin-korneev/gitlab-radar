const API = {
  dashboard: '/api/dashboard/', dependencies: '/api/dependency/', projects: '/api/project/', scan: '/api/scan/',
};
const PAGE_ROUTES = {
  dashboard: { page: 'dashboard' },
  projects: { page: 'projects' },
  dependencies: { page: 'dependencies', source: 'python', title: 'Зависимости', search: 'Найти зависимость' },
  images: { page: 'dependencies', source: 'docker', title: 'Образы контейнеров', search: 'Найти образ' },
  components: { page: 'dependencies', source: 'ci', title: 'CI-компоненты', search: 'Найти компонент' },
  webhooks: { page: 'dependencies', source: 'webhook', title: 'Webhooks', search: 'Найти webhook' },
  admin: { page: 'admin' },
};
const SOURCE_ROUTES = { python: 'dependencies', docker: 'images', ci: 'components', webhook: 'webhooks' };
const LEVEL_TITLES = { direct: 'Прямая', optional: 'Опциональная', transitive: 'Транзитивная' };
const RULE_TITLES = {
  'uv-required': 'uv', 'ruff-required': 'ruff', 'bandit-required': 'bandit', 'pylint-required': 'pylint',
  'python-linters-component-required': 'python-linters', 'sonar-component-required': 'sonar',
  'approved-registry-required': 'approved-registry',
  'aist-reviewer-hook-required': 'aist.reviewer',
};
const RULE_GROUPS = [
  { title: 'uv', rules: ['uv-required'] },
  { title: 'Линтеры', rules: ['ruff-required', 'bandit-required', 'pylint-required'] },
  { title: 'CI', rules: ['python-linters-component-required', 'sonar-component-required'] },
  { title: 'Registry', rules: ['approved-registry-required'] },
  { title: 'Webhook', rules: ['aist-reviewer-hook-required'] },
];
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
  selectedDependency: null, showTransitive: false, scanState: null, pollTimer: null,
  technologyTarget: null, projectsCount: 0, showSingleTechnologies: false,
  loaded: { dashboard: false, projects: false, dependencies: false, admin: false }, loading: {},
};

async function api(path, options = {}) {
  const response = await fetch(path, { cache: 'no-store', ...options });
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
    const loaders = { dashboard: loadDashboard, projects: loadProjects, dependencies: loadDependencies, admin: loadAdmin };
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
    const entry = element('button', `webhook-entry${hook.is_aist_reviewer ? ' webhook-required' : ''}`);
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
  const violations = Object.entries(RULE_TITLES)
    .filter(([code]) => results?.[code] === false)
    .map(([, title]) => title);
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
  compliance.classList.add(
    subproject.compliance < 50
      ? 'compliance-danger'
      : subproject.compliance < 80
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
  const version = item.version.split('.').map(Number);
  const row = element('button', 'compact-stat-link');
  row.type = 'button';
  if (version[0] < 3 || (version[0] === 3 && version[1] <= 10)) row.classList.add('python-version-danger');
  else if (version[0] === 3 && version[1] === 11) row.classList.add('python-version-warning');
  row.append(element('span', '', `Python ${item.version}`), element('b', '', String(item.projects_count)));
  row.addEventListener('click', () => openPythonVersion(item.version));
  return row;
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
  if (!dashboard.top_dependencies.length) topDependencies.append(element('p', 'empty-state', 'Зависимости ещё не найдены.'));

  const requirements = document.querySelector('#company-requirements');
  requirements.replaceChildren();
  const requirementsByCode = new Map(dashboard.company_requirements.map((item) => [item.code, item]));
  RULE_GROUPS.forEach((definition) => {
    const group = element('section', 'requirement-group');
    const items = element('div', 'requirement-group-items');
    definition.rules.forEach((code) => {
      const item = requirementsByCode.get(code);
      if (!item) return;
      const card = element('button', 'requirement');
      card.type = 'button';
      const progress = element('div', 'requirement-progress');
      const progressValue = element('span');
      progressValue.style.width = `${item.compliance_percentage}%`;
      progress.append(progressValue);
      card.append(
        element('strong', '', RULE_TITLES[code]),
        element('b', '', `${item.compliance_percentage}%`),
        progress,
        element('small', '', `${item.matching_projects} из ${item.total_projects}`),
      );
      card.title = item.description;
      card.addEventListener('click', () => openRuleViolations(code));
      items.append(card);
    });
    group.append(element('h4', '', definition.title), items);
    requirements.append(group);
  });

  const quality = dashboard.data_quality;
  renderDataQuality(quality);
  renderLastScan(dashboard.last_scan);
}
function renderDataQuality(quality) {
  document.querySelector('#data-quality-stats').replaceChildren(
    compactStatRow('Менеджер не определён', quality.unknown_package_manager),
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
  } else lastScan.append(element('p', 'empty-state', 'Сканирование ещё не запускалось.'));
}
async function loadDashboard() { renderDashboard(await api(API.dashboard)); state.loaded.dashboard = true; }
async function loadAdmin() {
  const dashboard = await api(API.dashboard);
  renderLastScan(dashboard.last_scan);
  renderDataQuality(dashboard.data_quality);
  state.loaded.admin = true;
}
async function loadProjects() {
  state.projects = await api(API.projects);
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
  let description = 'Сканирование ещё не запускалось.';
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
async function refreshScanStatus() {
  let retry = false;
  try {
    const previousState = state.scanState;
    const scan = await api(API.scan);
    state.scanState = scan.state;
    renderScanStatus(scan);
    if (previousState === 'running' && scan.state === 'completed') {
      state.dependencyCache = {};
      const reloads = [loadDashboard()];
      if (state.loaded.projects) reloads.push(loadProjects());
      if (state.loaded.dependencies) reloads.push(loadDependencies());
      await Promise.all(reloads);
    }
  } catch (error) {
    retry = true;
    showError(error);
  } finally {
    window.clearTimeout(state.pollTimer);
    state.pollTimer = state.scanState === 'running' || retry
      ? window.setTimeout(refreshScanStatus, retry ? 10000 : 3000)
      : null;
  }
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
document.querySelectorAll('.rule-switches input').forEach((input) => {
  input.addEventListener('change', renderProjects);
});
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
  try { await api(API.scan, { method: 'POST' }); } catch (error) { showError(error); }
  await refreshScanStatus();
});
showPage();
refreshScanStatus();
