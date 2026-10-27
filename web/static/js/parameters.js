async function ensureParameters() {
  if (!state.parameters.length) state.parameters = await api(API.parameters);
}
function renderParameters() {
  const fields = document.querySelector('#parameter-fields');
  fields.replaceChildren();
  state.parameters.forEach((parameter) => {
    if (parameter.value_type === 'percentage_range') {
      fields.append(percentageParameterField(parameter));
      return;
    }
    const label = element('label', 'parameter-field');
    const input = element('input');
    input.className = 'parameter-value-input';
    input.name = parameter.key;
    input.value = parameter.value;
    input.required = true;
    if (parameter.value_type === 'version') {
      input.inputMode = 'decimal';
      input.pattern = '\\d+\\.\\d+';
      input.placeholder = '3.11';
    } else if (parameter.value_type === 'integer') {
      input.type = 'number';
      input.step = '1';
      if (parameter.min_value !== null) input.min = parameter.min_value;
      if (parameter.max_value !== null) input.max = parameter.max_value;
    }
    label.append(element('strong', '', parameter.title), input);
    if (parameter.description) label.append(element('small', '', parameter.description));
    fields.append(label);
  });
}
function percentageParameterField(parameter) {
  const field = element('section', 'parameter-field percentage-parameter');
  const hidden = element('input');
  hidden.type = 'hidden';
  hidden.name = parameter.key;
  const minimum = parameter.min_value ?? 0;
  const maximum = parameter.max_value ?? 100;
  let [lowerValue, upperValue] = parameter.value.split(',').map(Number);
  const preview = element('div', 'threshold-preview');
  const danger = element('span', 'threshold-danger');
  const warning = element('span', 'threshold-warning');
  const success = element('span', 'threshold-success');
  preview.append(danger, warning, success);
  const slider = element('div', 'threshold-slider');
  const lower = element('input');
  const upper = element('input');
  [lower, upper].forEach((input) => {
    input.type = 'range';
    input.className = 'threshold-range-input';
    input.min = minimum;
    input.max = maximum;
    input.step = '1';
  });
  lower.setAttribute('aria-label', 'Начало зоны предупреждения');
  upper.setAttribute('aria-label', 'Начало успешной зоны');
  lower.value = lowerValue;
  upper.value = upperValue;
  const lowerOutput = element('output');
  const upperOutput = element('output');
  const values = element('div', 'threshold-values');
  const lowerLabel = element('span', 'threshold-value');
  const upperLabel = element('span', 'threshold-value');
  lowerLabel.append(element('span', '', 'Предупреждение'), lowerOutput);
  upperLabel.append(element('span', '', 'Успешно'), upperOutput);
  values.append(lowerLabel, upperLabel);
  slider.append(preview, lower, upper);
  function update(changed) {
    lowerValue = Number(lower.value);
    upperValue = Number(upper.value);
    if (lowerValue >= upperValue) {
      if (changed === lower) upperValue = Math.min(maximum, lowerValue + 1);
      else lowerValue = Math.max(minimum, upperValue - 1);
      lower.value = lowerValue;
      upper.value = upperValue;
    }
    hidden.value = `${lowerValue},${upperValue}`;
    lowerOutput.value = `${lowerValue}%`;
    upperOutput.value = `${upperValue}%`;
    const span = maximum - minimum || 1;
    danger.style.width = `${(lowerValue - minimum) / span * 100}%`;
    warning.style.width = `${(upperValue - lowerValue) / span * 100}%`;
    success.style.width = `${(maximum - upperValue) / span * 100}%`;
  }
  lower.addEventListener('input', () => update(lower));
  upper.addEventListener('input', () => update(upper));
  update();
  field.append(element('strong', '', parameter.title), slider, values, hidden);
  if (parameter.description) field.append(element('small', '', parameter.description));
  return field;
}
async function loadParametersPage() {
  await ensureParameters();
  renderParameters();
  state.loaded.parameters = true;
}
async function saveParameters() {
  const values = Object.fromEntries(state.parameters.map((parameter) => [
    parameter.key,
    document.querySelector(`#parameters-form [name="${parameter.key}"]`).value.trim(),
  ]));
  state.parameters = await api(API.parameters, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ values }),
  });
  state.loaded.dashboard = false;
  state.loaded.projects = false;
  state.loaded.requirements = false;
  state.requirementCatalog = null;
  renderParameters();
}
