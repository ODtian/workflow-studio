export function followTail(node, options) {
  let following = true;
  let key = options.key;
  let active = options.active ?? true;
  let frame;
  const scrollToEnd = () => {
    frame = undefined;
    if (active && following && node.clientHeight) node.scrollTop = node.scrollHeight;
  };
  const schedule = () => {
    if (active && frame === undefined) frame = requestAnimationFrame(scrollToEnd);
  };
  const onScroll = () => {
    if (!active || !node.clientHeight) return;
    following = node.scrollHeight - node.clientHeight - node.scrollTop < 48;
    options.onChange(following);
  };
  const observer = new ResizeObserver(schedule);
  observer.observe(node.firstElementChild);
  observer.observe(node);
  node.addEventListener('scroll', onScroll, {passive:true});
  schedule();
  return {
    update(next) {
      options = next;
      const resumed = !active && (next.active ?? true);
      active = next.active ?? true;
      if (next.key !== key || resumed) {
        key = next.key;
        following = true;
        options.onChange(true);
        schedule();
      }
    },
    destroy() {
      observer.disconnect();
      cancelAnimationFrame(frame);
      node.removeEventListener('scroll', onScroll);
    }
  };
}
