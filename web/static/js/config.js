const API = {
  authConfig: '/api/auth/config',
  authSession: '/api/auth/session',
  websocketTicket: '/api/auth/websocket-ticket',
  dashboard: '/api/dashboard/', dependencies: '/api/dependency/', projects: '/api/project/', scan: '/api/scan/',
  requirements: '/api/company-requirement/', requirementCatalog: '/api/company-requirement/catalog',
  requirementGroups: '/api/company-requirement-group/',
  parameters: '/api/application-parameter/',
  authorizedUsers: '/api/authorized-user/',
};
const AUTHENTICATED_ROUTES = new Set(['admin']);
const ADMINISTRATOR_ROUTES = new Set(['requirements', 'parameters', 'users']);
const PAGE_ROUTES = {
  dashboard: { page: 'dashboard' },
  projects: { page: 'projects' },
  dependencies: { page: 'dependencies', source: 'python', title: 'Зависимости', search: 'Найти зависимость' },
  images: { page: 'dependencies', source: 'docker', title: 'Образы контейнеров', search: 'Найти образ' },
  components: { page: 'dependencies', source: 'ci', title: 'CI-компоненты', search: 'Найти компонент' },
  webhooks: { page: 'dependencies', source: 'webhook', title: 'Webhooks', search: 'Найти webhook' },
  requirements: { page: 'requirements' },
  parameters: { page: 'parameters' },
  users: { page: 'users' },
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
  projectFilters: { query: '', rules: new Set() },
  selectedDependency: null, dependencyQuery: '', showTransitive: false, scanState: null, scanStatus: null,
  scanSocket: null, scanReconnectTimer: null,
  technologyTarget: null, projectsCount: 0, showSingleTechnologies: false,
  requirements: [], requirementGroups: [], requirementCatalog: null,
  parameters: [], authorizedUsers: [],
  auth: { config: null, tokens: null, user: null },
  currentRoute: null,
  selectedRequirementGroupId: null,
  loaded: { dashboard: false, projects: false, dependencies: false, requirements: false, parameters: false, users: false, admin: false }, loading: {},
};
const STATE_CHANNEL = typeof BroadcastChannel === 'undefined' ? null : new BroadcastChannel('gitlab-radar-state');

