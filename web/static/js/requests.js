import { api } from './api.js';
import { state } from './state.js';

const pendingReads = new Map();
const resources = new Map();
async function readLatest(key, load) {
  pendingReads.get(key)?.abort();
  const controller = new AbortController();
  pendingReads.set(key, controller);
  const version = state.dataVersion;
  const visibility = state.selectedVisibilityGroup;
  try {
    const value = await load(controller.signal);
    if (controller.signal.aborted || version !== state.dataVersion || visibility !== state.selectedVisibilityGroup) return null;
    return value;
  } catch (error) {
    if (controller.signal.aborted) return null;
    throw error;
  } finally {
    if (pendingReads.get(key) === controller) pendingReads.delete(key);
  }
}
function invalidateReads() {
  state.dataVersion += 1;
  pendingReads.forEach((controller) => controller.abort());
  pendingReads.clear();
  resources.clear();
}
async function ensureResource(key, path, apply) {
  if (!resources.has(key)) {
    const promise = readLatest(`resource:${key}`, (signal) => api(path, { signal })).then((value) => {
      if (value !== null) apply(value);
      else if (resources.get(key) === promise) resources.delete(key);
    }).catch((error) => {
      if (resources.get(key) === promise) resources.delete(key);
      throw error;
    });
    resources.set(key, promise);
  }
  await resources.get(key);
}

export { ensureResource, invalidateReads, readLatest };
