export function moveViewport(view, x, y) {
  const limit = (view.zoom - 1) / 2;
  return {...view, x:Math.max(-limit, Math.min(limit, x)), y:Math.max(-limit, Math.min(limit, y))};
}

export function zoomViewport(view, zoom, point = {x:0, y:0}) {
  zoom = Math.max(1, Math.min(8, zoom));
  const ratio = zoom / view.zoom;
  return moveViewport({...view, zoom}, point.x - (point.x - view.x) * ratio,
    point.y - (point.y - view.y) * ratio);
}
