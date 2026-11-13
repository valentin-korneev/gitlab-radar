function openDependency(...args) { return import('./dependencies.js').then((page) => page.openDependency(...args)); }
function openLanguageVersion(...args) { return import('./dependencies.js').then((page) => page.openLanguageVersion(...args)); }
function openRuleViolations(...args) { return import('./dependencies.js').then((page) => page.openRuleViolations(...args)); }
function showPage(...args) { return import('./router.js').then((page) => page.showPage(...args)); }
function ensurePageLoaded(...args) { return import('./router.js').then((page) => page.ensurePageLoaded(...args)); }
function connectScanStatusSocket(...args) { return import('./scan.js').then((page) => page.connectScanStatusSocket(...args)); }
export { openDependency, openLanguageVersion, openRuleViolations, showPage, ensurePageLoaded, connectScanStatusSocket };
