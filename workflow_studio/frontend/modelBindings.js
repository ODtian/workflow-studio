export function parameterFields(spec, model) {
  const controls = spec.model_controls?.[model] || [];
  return spec.fields.map(field => controls.find(control => control.key === field.key) || field);
}

export function fieldValue(field, value) {
  if (field.hidden) return field.default ?? '';
  if (field.type === 'select') {
    const choices = (field.options || []).map(option => typeof option === 'string' ? option : option.value);
    if (!choices.includes(value)) return field.default ?? '';
  }
  return value;
}

export function filesForModel(bindings, model, fields, definitions) {
  const saved = bindings[model] || {};
  return Object.fromEntries(fields.map(key => {
    const field = definitions.find(field => field.key === key);
    const fallback = ['mmproj', 'mtp'].includes(key) ? '' : field.default ?? '';
    return [key, fieldValue(field, saved[key] ?? fallback)];
  }));
}

export function bindingFromValues(values, fields) {
  return Object.fromEntries(fields.map(key => [key, values[key] ?? '']));
}
