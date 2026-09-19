'use strict';
// Pure functions shared by the live UI, synthetic demo, and regression tests.
function filterUsageRows(rows, from, through, selected) {
  return rows.filter(r => (!from || r.date >= from) && (!through || r.date <= through) && selected.has(r.model));
}
function summarizeSessions(rows) {
  const groups = new Map();
  const fields = ['tokens','requests','fresh_input_tokens','cache_read_tokens','cache_creation_tokens','output_tokens'];
  for (const r of rows) {
    const key = JSON.stringify([r.host,r.app,r.session_key]);
    if (!groups.has(key)) groups.set(key, {session_key:r.session_key,host:r.host,app:r.app,first:r.date,last:r.date,
      models:new Set(),cost:0,...Object.fromEntries(fields.map(f=>[f,0]))});
    const s = groups.get(key);
    s.first = s.first < r.date ? s.first : r.date;
    s.last = s.last > r.date ? s.last : r.date;
    s.models.add(r.model); s.cost += Number(r.cost_usd);
    for (const f of fields) s[f] += r[f];
  }
  return [...groups.values()].map(s=>({...s,models:[...s.models].sort()}));
}
if (typeof module !== 'undefined') module.exports = {filterUsageRows,summarizeSessions};
