function coordinatePath(dependency) {
  const parts = String(dependency.name || '')
    .replace(/^[a-z][a-z\d+.-]*:\/\//i, '').split('/').filter(Boolean);
  return { domain: parts.shift() || 'unknown-domain', endpoint: parts };
}
function webhookPath(dependency, version) {
  const endpoint = String(version.version || '');
  const suffixIndex = [endpoint.indexOf('?'), endpoint.indexOf('#')]
    .filter((index) => index >= 0).reduce((left, right) => Math.min(left, right), endpoint.length);
  const segments = endpoint.slice(0, suffixIndex).split('/').filter(Boolean);
  const suffix = endpoint.slice(suffixIndex);
  if (suffix) {
    if (segments.length) segments[segments.length - 1] += suffix;
    else segments.push(suffix);
  }
  return { domain: dependency.name || 'unknown-domain', endpoint: segments };
}
const coordinateAdapter = {
  tree: true,
  path: coordinatePath,
  searchTerms: (dependency) => [dependency.name],
  entryVersion: (version) => version.version,
  versionTitle: (version) => version.version || 'Версия не указана',
};
const CATALOG_ADAPTERS = {
  python: { ...coordinateAdapter, tree: false, title: 'Зависимости', search: 'Найти зависимость' },
  docker: { ...coordinateAdapter, title: 'Образы контейнеров', search: 'Найти образ' },
  ci: { ...coordinateAdapter, title: 'CI-компоненты', search: 'Найти компонент' },
  webhook: {
    ...coordinateAdapter, title: 'Webhooks', search: 'Найти webhook',
    path: webhookPath,
    searchTerms: (dependency, version) => [dependency.name, version.version || ''],
    entryVersion: () => null,
    versionTitle: (version) => version.version || 'Webhook',
  },
};
function catalogAdapter(source) { return CATALOG_ADAPTERS[source]; }

export { CATALOG_ADAPTERS, catalogAdapter };
