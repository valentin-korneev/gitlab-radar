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
function complianceTone(value, parameterKey) {
  const [dangerThreshold, successThreshold] = parameterRange(parameterKey);
  if (value < dangerThreshold) return 'danger';
  if (value < successThreshold) return 'warning';
  return 'success';
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
      const tone = complianceTone(item.compliance_percentage, 'company_requirement_thresholds');
      const card = element('button', `requirement requirement-${tone}`);
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

async function loadDashboard() {
  const [dashboard] = await Promise.all([api(API.dashboard), ensureRequirements(), ensureParameters()]);
  renderDashboard(dashboard);
  state.loaded.dashboard = true;
}
