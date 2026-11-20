// Refresh Myfxbook's official Small widgets without carrying forward a browser-cached image.
(() => {
  const every = 15 * 60 * 1000;
  const widgets = new Map();
  for (const img of document.querySelectorAll('img[data-myfxbook-widget]')) {
    const id = img.dataset.myfxbookWidget;
    if (!/^\d+$/.test(id)) continue;
    if (!widgets.has(id)) widgets.set(id, []);
    widgets.get(id).push(img);
  }
  let last = -1;
  function refresh() {
    if (document.hidden) return;
    const bucket = Math.floor(Date.now() / every);
    if (bucket === last) return;
    last = bucket;
    for (const [id, images] of widgets) {
      // This is the CDN URL that the documented small.jpg embed redirects to.
      const src = 'https://widget.mfbcdn.net/widget/widget.png?accountOid=' + id + '&type=4&v=' + bucket;
      const image = new Image();
      image.onload = () => {
        if (last === bucket) for (const node of images) node.src = src;
      };
      image.src = src;
    }
  }
  refresh();
  document.addEventListener('visibilitychange', refresh);
  setInterval(refresh, every);
})();
