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


function projectMatchesFilters(project) {
  const query = state.projectFilters.query.trim().toLowerCase();
  const rules = [...state.projectFilters.rules];
  const pythonVersions = project.subprojects
    .map((item) => normalizePythonVersion(item.python_version || item.python_constraint))
    .filter(Boolean)
    .map((version) => `Python ${version}`)
    .join(' ');
  const searchable = `${project.name} ${project.path_with_namespace} ${project.subprojects.map((item) => item.path).join(' ')} ${pythonVersions}`.toLowerCase();
  return (!query || searchable.includes(query))
    && rules.every((rule) => project.company_rule_results?.[rule] === false);
}
function syncProjectFilterControls() {
  document.querySelector('#project-search').value = state.projectFilters.query;
  document.querySelectorAll('.rule-switches input').forEach((input) => {
    input.checked = state.projectFilters.rules.has(input.dataset.rule);
  });
}
function resetProjectFilters() {
  state.projectFilters.query = '';
  state.projectFilters.rules.clear();
  syncProjectFilterControls();
  if (state.loaded.projects) renderProjects();
}
function clearProjectSelection() {
  state.selectedId = null;
  state.selectedSubprojectPath = null;
  document.querySelector('#project-detail').replaceChildren(
    element('p', 'empty-state', 'Выберите проект, чтобы посмотреть детали.'),
  );
}
function renderProjects() {
  const projects = state.projects.filter(projectMatchesFilters);
  if (state.selectedId !== null && !projects.some((project) => project.id === state.selectedId)) {
    clearProjectSelection();
  }
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
  compliance.classList.add(`compliance-${complianceTone(subproject.compliance, 'project_compliance_thresholds')}`);
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

