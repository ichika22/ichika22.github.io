/* Only the combined result and its source date change; Myfxbook widgets stay intact. */
(() => {
  'use strict';
  const url = 'https://raw.githubusercontent.com/ichika22/ichika22.github.io/refs/heads/esora-performance-data/myfxbook-combined.json';
  const ids = new Set(['12290460', '12290478', '12290493', '12290520']);
  const nodes = [...document.querySelectorAll('[data-combined-account]')];
  if (!nodes.length) return;
  const ja = document.documentElement.lang.toLowerCase().startsWith('ja');
  const number = new Intl.NumberFormat(ja ? 'ja-JP' : 'en-US', {
    minimumFractionDigits: 1, maximumFractionDigits: 1, signDisplay: 'exceptZero',
  });
  const period = 15 * 60 * 1000;
  let loading = false;

  function sourceTimestamp(value) {
    if (typeof value !== 'string') return null;
    const m = value.match(/^(\d{2})\/(\d{2})\/(\d{4}) (\d{2}):(\d{2})$/);
    if (!m) return null;
    // Sort and compare calendar dates only; Myfxbook's API does not declare TZ.
    const day = `${m[3]}-${m[1]}-${m[2]}`;
    const stamp = `${day}T${m[4]}:${m[5]}`;
    const check = Date.parse(stamp + 'Z');
    if (!Number.isFinite(check) || !new Date(check).toISOString().startsWith(stamp)) return null;
    return { day, stamp, calendarAge: Date.now() - Date.parse(day + 'T00:00:00Z') };
  }

  function show(payload) {
    if (payload?.version !== 1 || !payload.accounts || typeof payload.accounts !== 'object') return;
    for (const node of nodes) {
      const id = node.dataset.combinedAccount;
      if (!ids.has(id) || !Object.hasOwn(payload.accounts, id)) continue;
      const record = payload.accounts[id];
      if (!record || !Number.isFinite(record.gain) || record.gain < -100 || record.gain > 100000000
          || !Number.isFinite(record.combined) || record.combined < -100 || record.combined > 400000000) continue;
      const time = sourceTimestamp(record.sourceUpdated);
      if (!time || time.day <= node.dataset.combinedBaseline
          || time.stamp < (node.dataset.combinedDisplayed || '')
          || time.calendarAge < -86400000) continue;
      const value = node.querySelector('[data-combined-value]');
      const updated = node.querySelector('[data-combined-updated]');
      if (!value || !updated) continue;
      const stale = time.calendarAge >= 3 * 86400000;
      const displayTime = time.stamp.replace('T', ' ');
      value.textContent = number.format(record.combined) + '%';
      updated.textContent = ja
        ? `Myfxbook更新 ${displayTime}${stale ? '（更新が遅れています）' : ''}`
        : `Myfxbook updated ${displayTime}${stale ? ' (delayed)' : ''}`;
      node.dataset.combinedDisplayed = time.stamp;
    }
  }

  async function refresh() {
    if (loading || document.visibilityState === 'hidden') return;
    loading = true;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch(url, {
        cache: 'no-store', credentials: 'omit', redirect: 'error',
        referrerPolicy: 'no-referrer', signal: controller.signal,
      });
      if (response.ok) show(await response.json());
    } catch (_) {
      // Preserve dated HTML fallback or the last verified update in this tab.
    } finally {
      clearTimeout(timer);
      loading = false;
    }
  }
  refresh();
  setInterval(refresh, period);
  document.addEventListener('visibilitychange', () => refresh());
})();
