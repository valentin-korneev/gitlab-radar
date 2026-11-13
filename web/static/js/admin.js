import { api } from './api.js';
import { API } from './config.js';
import { renderDataQuality, renderLastScan } from './dashboard.js';
import { readLatest } from './requests.js';
import { connectScanStatusSocket } from './scan.js';
import { state } from './state.js';

async function loadAdmin() {
  const dashboard = await readLatest('admin', (signal) => api(API.dashboard, { signal }));
  if (!dashboard) return;
  renderLastScan(dashboard.last_scan);
  renderDataQuality(dashboard.data_quality);
  await connectScanStatusSocket();
  state.loaded.admin = true;
}

export { loadAdmin };
