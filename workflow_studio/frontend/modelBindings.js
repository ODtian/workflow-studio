export function filesForModel(bindings, model, fields) {
  const saved = bindings[model] || {};
  return Object.fromEntries(fields.map(key => [key, saved[key] || '']));
}

export function bindingFromValues(values, fields) {
  return Object.fromEntries(fields.map(key => [key, values[key] || '']));
}
