import { showError, showSuccess } from './toasts.js';

const pendingEditors = new WeakSet();
async function runEditorAction(control, action) {
  if (pendingEditors.has(control)) return;
  pendingEditors.add(control);
  const controls = control.matches('button, input') ? [control] : [...control.querySelectorAll('button, input, select, textarea')];
  const disabled = controls.map((item) => item.disabled);
  controls.forEach((item) => { item.disabled = true; });
  try { return await action(); }
  finally {
    pendingEditors.delete(control);
    controls.forEach((item, index) => { item.disabled = disabled[index]; });
  }
}
function bindEditorAction(control, action, scope = control) {
  control.addEventListener('click', () => runEditorAction(scope, action).catch(showError));
}
function bindEditorForm(selector, action) {
  const form = document.querySelector(selector);
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    runEditorAction(form, () => action(event)).catch(showError);
  });
}
function bindAsyncInput(input, { read, save, onSaved, success, scope = input, normalize = (value) => value.trim() }) {
  input.addEventListener('change', () => runEditorAction(scope, async () => {
    const value = normalize(input.value);
    if (value === read()) return;
    const updated = await save(value);
    onSaved(updated);
    input.value = read() ?? '';
    showSuccess(success);
  }).catch(showError));
}

function bindEditorChange(input, scope, action) {
  input.addEventListener('change', () => runEditorAction(scope, action).catch(showError));
}

export { bindAsyncInput, bindEditorAction, bindEditorForm, bindEditorChange, runEditorAction };
