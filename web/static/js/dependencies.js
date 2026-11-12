function renderDependencies() {
  if (['docker', 'ci', 'webhook'].includes(state.dependencySource)) {
    renderEndpointDependencies();
    return;
  }
  const query = state.dependencyQuery.trim().toLowerCase();
  const dependencies = state.dependencies
    .map((dependency) => ({ dependency, visible: visibleDependencyData(dependency) }))
    .filter(({ dependency, visible }) => {
      const searchable = state.dependencySource === 'webhook'
        ? [dependency.name, ...dependency.versions.map((version) => version.version || '')]
        : [dependency.name];
      return searchable.some((value) => (
        state.dependencySource === 'webhook' ? maskWebhookText(value) : value
      ).toLowerCase().includes(query)) && visible.projectsCount;
    });
  if (state.selectedDependency && !dependencies.some(({ dependency }) => dependency.name === state.selectedDependency)) {
    clearDependencySelection();
  }
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
      ? `${visible.languages.map((language) => languageDisplayName(language)).join(', ') || 'язык не указан'} · ${levels} · вариантов версий: ${visible.versions.length}`
      : state.dependencySource === 'webhook'
        ? `хуков: ${visible.versions.length}`
        : `вариантов версий: ${visible.versions.length}`;
    identity.append(element('strong', '', dependency.name), element('small', '', metadata));
    row.append(identity, element('b', '', visible.projectsCount));
    row.addEventListener('click', () => selectDependency(dependency, row));
    list.append(row);
  });
}
function renderEndpointDependencies() {
  const source = state.dependencySource;
  const query = state.dependencyQuery.trim().toLowerCase();
  const roots = new Map();
  const nodes = new Map();
  state.dependencies.forEach((dependency) => {
    const domainMatches = source === 'webhook' && maskWebhookText(dependency.name).toLowerCase().includes(query);
    dependency.versions.forEach((version) => {
      const matchesQuery = !query || (source === 'webhook'
        ? domainMatches || maskWebhookText(version.version || '').toLowerCase().includes(query)
        : dependency.name.toLowerCase().includes(query));
      const { domain, endpoint } = endpointPath(source, dependency, version);
      if (!domain) return;
      let node = roots.get(domain);
      if (!node) {
        node = createEndpointTreeNode(source, [domain]);
        roots.set(domain, node);
      }
      let path = [domain];
      endpoint.forEach((segment) => {
        path = [...path, segment];
        let child = node.children.get(segment);
        if (!child) {
          child = createEndpointTreeNode(source, path);
          child.parent = node;
          node.children.set(segment, child);
        }
        node = child;
      });
      addEndpointTreeEntry(node, source === 'webhook' ? null : version.version, version.projects, matchesQuery);
    });
  });
  roots.forEach((node) => {
    countEndpointTreeProjects(node);
    setEndpointTreeVisibility(node, query);
  });
  const orderedRoots = [...roots.values()].filter((node) => node.visible).sort(compareEndpointTreeNodes);
  const list = document.querySelector('#dependency-list');
  list.replaceChildren();
  if (!orderedRoots.length) {
    list.append(element('p', 'empty-state', state.dependencies.length ? 'Элементы не найдены.' : 'Список пуст.'));
    if (state.selectedDependency) clearDependencySelection();
    return;
  }
  const registerNodes = (node) => {
    node.fullPath = node.parent ? `${node.parent.fullPath}/${node.segment}` : node.segment;
    nodes.set(node.key, node);
    node.visibleChildren.forEach(registerNodes);
  };
  orderedRoots.forEach(registerNodes);
  let selectedNode = nodes.get(state.selectedDependency);
  if (!selectedNode && state.selectedDependency) {
    selectedNode = [...nodes.values()].find((node) => (
      node.fullPath === state.selectedDependency
      || (!node.parent && node.segment === state.selectedDependency)
    ));
    if (selectedNode) {
      state.selectedDependency = selectedNode.key;
      for (let parent = selectedNode.parent; parent; parent = parent.parent) {
        state.dependencyTreeExpanded.add(parent.key);
      }
    }
  }
  if (state.selectedDependency && !selectedNode) clearDependencySelection();
  const selectedPath = new Set();
  for (let node = selectedNode; node; node = node.parent) selectedPath.add(node.key);
  orderedRoots.forEach((node) => renderEndpointTreeNode(node, list, source, selectedPath));
  if (selectedNode) renderDependencyDetail(endpointTreeDependency(selectedNode, source));
}
function endpointPath(source, dependency, version) {
  if (source === 'webhook') {
    const endpoint = String(version.version || '');
    const suffixIndex = [endpoint.indexOf('?'), endpoint.indexOf('#')]
      .filter((index) => index >= 0)
      .reduce((left, right) => Math.min(left, right), endpoint.length);
    const path = endpoint.slice(0, suffixIndex);
    const suffix = endpoint.slice(suffixIndex);
    const segments = path.split('/').filter(Boolean);
    if (suffix) {
      if (segments.length) segments[segments.length - 1] += suffix;
      else segments.push(suffix);
    }
    return { domain: dependency.name || 'unknown-domain', endpoint: segments };
  }
  const parts = String(dependency.name || '')
    .replace(/^[a-z][a-z\d+.-]*:\/\//i, '')
    .split('/')
    .filter(Boolean);
  return { domain: parts.shift() || 'unknown-domain', endpoint: parts };
}
function createEndpointTreeNode(source, path) {
  return {
    key: JSON.stringify([source, ...path]),
    segment: path[path.length - 1],
    path,
    parent: null,
    children: new Map(),
    entries: new Map(),
  };
}
function addEndpointTreeEntry(node, version, projects, matchesQuery) {
  const key = version ?? '';
  if (!node.entries.has(key)) node.entries.set(key, { version, projects: new Map(), matchesQuery: false });
  const entry = node.entries.get(key);
  entry.matchesQuery ||= matchesQuery;
  projects.forEach((project) => {
    entry.projects.set(`${project.id}:${project.subproject_path}`, project);
  });
}
function countEndpointTreeProjects(node) {
  const projectIds = new Set();
  node.entries.forEach((entry) => entry.projects.forEach((project) => projectIds.add(project.id)));
  node.children.forEach((child) => countEndpointTreeProjects(child).forEach((id) => projectIds.add(id)));
  node.projectsCount = projectIds.size;
  return projectIds;
}
function setEndpointTreeVisibility(node, query) {
  node.visibleChildren = [...node.children.values()]
    .filter((child) => setEndpointTreeVisibility(child, query))
    .sort(compareEndpointTreeNodes);
  node.visible = !query || [...node.entries.values()].some((entry) => entry.matchesQuery) || node.visibleChildren.length > 0;
  return node.visible;
}
function compareEndpointTreeNodes(left, right) {
  const leftHasChildren = left.children.size > 0;
  const rightHasChildren = right.children.size > 0;
  if (leftHasChildren !== rightHasChildren) return leftHasChildren ? -1 : 1;
  return right.projectsCount - left.projectsCount || left.segment.localeCompare(right.segment);
}
function endpointTreeRecords(node, relativePath = []) {
  const records = [...node.entries.values()].map((entry) => ({
    path: relativePath,
    version: entry.version,
    projects: [...entry.projects.values()],
  }));
  node.children.forEach((child) => records.push(...endpointTreeRecords(child, [...relativePath, child.segment])));
  return records;
}
function endpointTreeProjectCount(node) {
  return node.projectsCount;
}
function endpointTreeDependency(node, source) {
  const records = endpointTreeRecords(node);
  const versions = records.map((record) => ({
    version: [record.path.join('/'), record.version].filter(Boolean).join(' · ') || null,
    projects: record.projects,
  }));
  return {
    name: source === 'webhook' ? maskWebhookText(node.fullPath) : node.fullPath,
    level: 'direct',
    levels: ['direct'],
    projects_count: endpointTreeProjectCount(node),
    languages: [],
    versions,
  };
}
function renderEndpointTreeNode(node, container, source, selectedPath) {
  const inSelectionPath = selectedPath.has(node.key);
  const wrapper = element('div', `dependency-tree-node${inSelectionPath ? ' in-selection-path' : ''}`);
  const row = element('div', 'dependency-tree-row');
  const hasChildren = node.visibleChildren.length > 0;
  if (hasChildren) {
    const toggle = element('button', 'dependency-tree-toggle', state.dependencyTreeExpanded.has(node.key) ? '−' : '+');
    toggle.type = 'button';
    toggle.setAttribute('aria-label', `${state.dependencyTreeExpanded.has(node.key) ? 'Свернуть' : 'Раскрыть'} ${maskWebhookText(node.segment)}`);
    toggle.setAttribute('aria-expanded', String(state.dependencyTreeExpanded.has(node.key)));
    toggle.addEventListener('click', () => {
      if (state.dependencyTreeExpanded.has(node.key)) state.dependencyTreeExpanded.delete(node.key);
      else state.dependencyTreeExpanded.add(node.key);
      renderDependencies();
    });
    row.append(toggle);
  } else row.append(element('span', 'dependency-tree-spacer'));
  const isSelected = state.selectedDependency === node.key;
  const select = element('button', `dependency-tree-select${isSelected ? ' active' : ''}${inSelectionPath ? ' in-selection-path' : ''}`);
  select.type = 'button';
  select.setAttribute('aria-pressed', String(isSelected));
  select.append(element('span', '', source === 'webhook' ? maskWebhookText(node.segment) : node.segment));
  select.append(element('b', '', String(endpointTreeProjectCount(node))));
  select.addEventListener('click', () => {
    state.selectedDependency = node.key;
    renderDependencies();
  });
  row.append(select);
  wrapper.append(row);
  if (hasChildren) {
    const children = element('div', 'dependency-tree-children');
    children.hidden = !state.dependencyTreeExpanded.has(node.key);
    node.visibleChildren.forEach((child) => renderEndpointTreeNode(child, children, source, selectedPath));
    wrapper.append(children);
  }
  container.append(wrapper);
}
function clearDependencySelection() {
  state.selectedDependency = null;
  document.querySelector('#dependency-detail').replaceChildren(
    element('p', 'empty-state', 'Выберите элемент, чтобы посмотреть версии и проекты.'),
  );
}
function resetDependencyPage() {
  state.dependencyQuery = '';
  state.showTransitive = false;
  state.dependencyLanguages.clear();
  state.dependencyLanguagesInitialized = false;
  document.querySelector('#dependency-search').value = '';
  document.querySelector('#show-transitive').checked = false;
  clearDependencySelection();
}
function visibleDependencyData(dependency) {
  const versions = dependency.versions
    .map((version) => ({
      ...version,
      projects: version.projects.filter((project) => (
        (state.dependencySource !== 'python' || state.showTransitive || project.level !== 'transitive')
        && (state.dependencySource !== 'python'
          || state.dependencyLanguages.has(canonicalLanguageCode(project.language)))
      )),
    }))
    .filter((version) => version.projects.length);
  const projects = versions.flatMap((version) => version.projects);
  const levels = [...new Set(projects.map((project) => project.level))];
  return {
    versions,
    levels: dependency.levels.filter((level) => levels.includes(level)),
    languages: [...new Set(
      projects.map((project) => canonicalLanguageCode(project.language)).filter(Boolean),
    )].sort(),
    projectsCount: new Set(projects.map((project) => project.id)).size,
  };
}
function renderDependencyDetail(dependency) {
  const detail = document.querySelector('#dependency-detail');
  detail.replaceChildren();
  const visible = visibleDependencyData(dependency);
  detail.append(element('h3', '', dependency.name));
  if (state.dependencySource === 'python') appendDetail(detail, 'Типы использования', visible.levels.map((level) => LEVEL_TITLES[level]).join(', '));
  if (state.dependencySource === 'python') {
    appendDetail(detail, 'Языки', visible.languages.map((language) => languageDisplayName(language)).join(', '));
  }
  appendDetail(detail, 'Используется в проектах', String(visible.projectsCount));
  const versions = element('div', 'dependency-versions');
  visible.versions.forEach((version) => {
    const group = element('section', 'dependency-version');
    const versionTitle = state.dependencySource === 'webhook'
      ? maskWebhookText(version.version || 'Webhook')
      : version.version || 'Версия не указана';
    group.append(element('h4', '', versionTitle));
    const projects = element('div', 'dependency-projects');
    version.projects.forEach((project) => {
      const link = element('a', 'dependency-project');
      link.href = project.web_url;
      link.target = '_blank';
      link.rel = 'noreferrer';
      link.append(
        element('strong', '', project.path_with_namespace),
        element('small', '', `${project.subproject_path === '.' ? 'Корень репозитория' : project.subproject_path}${state.dependencySource === 'python' ? ` · ${languageDisplayName(project.language || '', project.language || 'язык не указан')} · ${LEVEL_TITLES[project.level]}` : ''}`),
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
let dependencyLoadId = 0;
async function loadDependencies() {
  const source = state.dependencySource;
  const loadId = ++dependencyLoadId;
  let cache = state.dependencyCache;
  while (!cache[source]) {
    let dependencies;
    try {
      dependencies = await api(`${API.dependencies}?source=${source}`);
    } catch (error) {
      if (loadId !== dependencyLoadId || source !== state.dependencySource) return;
      if (cache !== state.dependencyCache) {
        cache = state.dependencyCache;
        continue;
      }
      throw error;
    }
    if (loadId !== dependencyLoadId || source !== state.dependencySource) return;
    if (cache !== state.dependencyCache) {
      cache = state.dependencyCache;
      continue;
    }
    cache[source] = dependencies;
  }
  state.dependencies = cache[source];
  const languages = [...new Set(
    state.dependencies.flatMap((dependency) => dependency.languages || []).map(canonicalLanguageCode),
  )].sort();
  if (!state.dependencyLanguagesInitialized) {
    state.dependencyLanguages = new Set(languages);
    state.dependencyLanguagesInitialized = true;
  } else {
    state.dependencyLanguages = new Set(
      [...state.dependencyLanguages]
        .map(canonicalLanguageCode)
        .filter((language) => languages.includes(language)),
    );
  }
  renderDependencyLanguageOptions(languages);
  state.loaded.dependencies = true;
  renderDependencies();
  const selected = state.dependencies.find((dependency) => dependency.name === state.selectedDependency);
  if (selected) renderDependencyDetail(selected);
}
function renderDependencyLanguageOptions(languages) {
  const options = document.querySelector('#dependency-language-options');
  options.replaceChildren(...languages.map((language) => {
    const label = element('label', 'requirement-language-option');
    const input = element('input');
    input.type = 'checkbox';
    input.checked = state.dependencyLanguages.has(language);
    input.addEventListener('change', () => {
      if (input.checked) state.dependencyLanguages.add(language);
      else state.dependencyLanguages.delete(language);
      renderDependencies();
      const selected = state.dependencies.find((dependency) => dependency.name === state.selectedDependency);
      if (selected) renderDependencyDetail(selected);
    });
    label.append(input, element('span', '', languageDisplayName(language)));
    return label;
  }));
  if (!languages.length) options.append(element('small', 'muted', 'Нет языков'));
}
async function openDependency(name, source = 'python') {
  state.dependencySource = source;
  document.querySelector('#transitive-filter').classList.toggle('control-placeholder', source !== 'python');
  state.selectedDependency = name;
  const route = SOURCE_ROUTES[source];
  if (window.location.hash !== `#${route}`) {
    window.location.hash = route;
    return;
  }
  await loadDependencies();
}
async function openRuleViolations(code) {
  state.projectFilters.query = '';
  state.projectFilters.rules = new Set([code]);
  state.projectFilters.language = null;
  state.projectFilters.version = null;
  syncProjectFilterControls();
  window.location.hash = 'projects';
  await ensurePageLoaded('projects');
  renderProjects();
}
async function openLanguageVersion(language, version) {
  state.projectFilters.rules.clear();
  state.projectFilters.query = `${language.name} ${version}`;
  state.projectFilters.language = language.code;
  state.projectFilters.version = version;
  syncProjectFilterControls();
  if (window.location.hash !== '#projects') {
    window.location.hash = 'projects';
  }
  await ensurePageLoaded('projects');
  renderProjects();
}

