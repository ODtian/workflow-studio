export function bytes(value) {
  if (!value) return '0 B';
  const units = ['B','KB','MB','GB','TB'];
  const scale = Math.min(Math.floor(Math.log(value)/Math.log(1024)),4);
  return `${(value/1024**scale).toFixed(scale ? 1 : 0)} ${units[scale]}`;
}

export const taskStatus = {queued:'等待中',running:'传输中',completed:'已完成',failed:'失败',cancelled:'已停止'};
