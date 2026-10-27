async function loadAdmin() {
  const dashboard = await api(API.dashboard);
  renderLastScan(dashboard.last_scan);
  renderDataQuality(dashboard.data_quality);
  await connectScanStatusSocket();
  state.loaded.admin = true;
}
