export function followTail(node, options) {
  let following = true;
  let key = options.key;
  let active = options.active ?? true;
  let reset = options.reset;
  let frame;
  let position = node.scrollTop;
  const setFollowing = value => {
    following = value;
    options.onChange(value);
  };
  const scrollToEnd = () => {
    frame = undefined;
    if (active && following && node.clientHeight) {
      node.scrollTop = node.scrollHeight;
      position = node.scrollTop;
    }
  };
  const schedule = () => {
    if (active && following && frame === undefined) frame = requestAnimationFrame(scrollToEnd);
  };
  const onScroll = () => {
    if (!active || !node.clientHeight) return;
    const next = node.scrollTop;
    if (next < position) setFollowing(false);
    else if (node.scrollHeight - node.clientHeight - next < 8) setFollowing(true);
    position = next;
  };
  const onWheel = event => {if (event.deltaY < 0) setFollowing(false);};
  const observer = new ResizeObserver(schedule);
  observer.observe(node.firstElementChild);
  observer.observe(node);
  node.addEventListener('scroll', onScroll, {passive:true});
  node.addEventListener('wheel', onWheel, {passive:true});
  schedule();
  return {
    update(next) {
      options = next;
      const resumed = !active && (next.active ?? true);
      active = next.active ?? true;
      if (next.key !== key || next.reset !== reset) {
        key = next.key;
        reset = next.reset;
        setFollowing(true);
        schedule();
      } else if (resumed) schedule();
    },
    destroy() {
      observer.disconnect();
      cancelAnimationFrame(frame);
      node.removeEventListener('scroll', onScroll);
      node.removeEventListener('wheel', onWheel);
    }
  };
}
