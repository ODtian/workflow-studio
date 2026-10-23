export function dimensionsForMP(megapixels, ratio, step = 16) {
  const area = megapixels * 1_000_000;
  return {
    width: Math.max(step, Math.round(Math.sqrt(area * ratio) / step) * step),
    height: Math.max(step, Math.round(Math.sqrt(area / ratio) / step) * step)
  };
}
