import { CATALOG_ADAPTERS } from './catalog-adapters.js';

const API = {
  authConfig: '/api/auth/config',
  authSession: '/api/auth/session',
  websocketTicket: '/api/auth/websocket-ticket',
  dashboard: '/api/dashboard/', dependencies: '/api/dependency/', projects: '/api/project/', scan: '/api/scan/',
  requirements: '/api/company-requirement/', requirementCatalog: '/api/company-requirement/catalog',
  requirementGroups: '/api/company-requirement-group/',
  parameters: '/api/application-parameter/',
  authorizedUsers: '/api/authorized-user/',
  visibility: '/api/visibility/',
  visibilityAdmin: '/api/visibility/admin/',
  programmingLanguages: '/api/programming-language/',
  projectBlacklist: '/api/project-blacklist/',
};
const AUTHENTICATED_ROUTES = new Set([
  'visibility', 'admin',
]);
const ADMINISTRATOR_ROUTES = new Set(['requirements', 'parameters', 'languages', 'users', 'visibility-admin', 'blacklist']);
const PAGE_ROUTES = {
  dashboard: { page: 'dashboard' },
  projects: { page: 'projects' },
  dependencies: { page: 'dependencies', source: 'python', ...CATALOG_ADAPTERS.python },
  images: { page: 'dependencies', source: 'docker', ...CATALOG_ADAPTERS.docker },
  components: { page: 'dependencies', source: 'ci', ...CATALOG_ADAPTERS.ci },
  webhooks: { page: 'dependencies', source: 'webhook', ...CATALOG_ADAPTERS.webhook },
  requirements: { page: 'requirements' },
  parameters: { page: 'parameters' },
  languages: { page: 'languages' },
  users: { page: 'users' },
  visibility: { page: 'visibility' },
  'visibility-admin': { page: 'visibility-admin' },
  blacklist: { page: 'blacklist' },
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
const STATE_CHANNEL = typeof BroadcastChannel === 'undefined' ? null : new BroadcastChannel('gitlab-radar-state');


export { ADMINISTRATOR_ROUTES, API, AUTHENTICATED_ROUTES, HOOK_EVENT_TITLES, LEVEL_TITLES, PAGE_ROUTES, PHASE_TITLES, SOURCE_ROUTES, STATE_CHANNEL };
