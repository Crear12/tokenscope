'use strict';
function modelsInDateRange(rows, from, through) {
  return new Set(rows.filter(r => (!from || r.date >= from) && (!through || r.date <= through)).map(r => r.model));
}
function matchingModels(models, search) {
  const query = search.toLowerCase();
  return [...models].filter(model => model.toLowerCase().includes(query)).sort();
}
// Pure functions shared by the live UI, synthetic demo, and regression tests.
function filterUsageRows(rows, from, through, selected) {
  return rows.filter(r => (!from || r.date >= from) && (!through || r.date <= through) && selected.has(r.model));
}
function sessionIdentity(row) {
  return JSON.stringify([row.host,row.app,row.session_key]);
}
function summarizeSessions(rows) {
  const groups = new Map();
  const fields = ['tokens','requests','fresh_input_tokens','cache_read_tokens','cache_creation_tokens','output_tokens'];
  for (const r of rows) {
    const key = sessionIdentity(r);
    if (!groups.has(key)) groups.set(key, {session_key:r.session_key,title:r.session_title||'',host:r.host,app:r.app,first:r.date,last:r.date,
      models:new Set(),cost:0,...Object.fromEntries(fields.map(f=>[f,0]))});
    const s = groups.get(key);
    s.first = s.first < r.date ? s.first : r.date;
    s.last = s.last > r.date ? s.last : r.date;
    s.models.add(r.model); s.cost += Number(r.cost_usd);
    for (const f of fields) s[f] += r[f];
  }
  return [...groups.values()].map(s=>({...s,models:[...s.models].sort()}));
}
function sessionDetails(rows, key) {
  const selected = rows.filter(r => sessionIdentity(r) === key);
  const session = summarizeSessions(selected)[0] || null;
  const fields = ['tokens','requests','fresh_input_tokens','cache_read_tokens','cache_creation_tokens','output_tokens'];
  const summarize = (dimension) => {
    const groups = new Map();
    for (const r of selected) {
      const value = r[dimension];
      if (!groups.has(value)) groups.set(value, {value,models:new Set(),cost:0,...Object.fromEntries(fields.map(f=>[f,0]))});
      const group = groups.get(value);
      group.models.add(r.model); group.cost += Number(r.cost_usd);
      for (const field of fields) group[field] += r[field];
    }
    return [...groups.values()].map(group => ({...group,models:[...group.models].sort()}));
  };
  return {session,daily:summarize('date').sort((a,b)=>a.value.localeCompare(b.value)),
          models:summarize('model').sort((a,b)=>b.tokens-a.tokens||a.value.localeCompare(b.value))};
}
function sessionMatrix(rows, from, through) {
  const sessions = new Map();
  for (const r of rows) {
    const key = sessionIdentity(r);
    if (!sessions.has(key)) sessions.set(key,{key,title:r.session_title||'',host:r.host,app:r.app,total:0,days:new Map()});
    const s = sessions.get(key);
    if (r.session_title) s.title = r.session_title;
    s.total += r.tokens;
    s.days.set(r.date,(s.days.get(r.date)||0)+r.tokens);
  }
  const ordered = [...sessions.values()].sort((a,b)=>b.total-a.total||a.key.localeCompare(b.key));
  const observed = rows.map(r=>r.date).sort(), dates = [];
  if (observed.length) {
    const end = Date.parse((through||observed.at(-1))+'T00:00:00Z');
    for (let t=Date.parse((from||observed[0])+'T00:00:00Z');t<=end;t+=86400000) dates.push(new Date(t).toISOString().slice(0,10));
  }
  let min=Infinity,max=-Infinity;
  for (const s of ordered) for (const value of s.days.values()) { min=Math.min(min,value); max=Math.max(max,value); }
  return {sessions:ordered,dates,min:ordered.length?min:0,max:ordered.length?max:0};
}
function jetColor(value,min,max) {
  const t = max===min ? .5 : Math.max(0,Math.min(1,(value-min)/(max-min)));
  const channel = center=>Math.round(255*Math.max(0,Math.min(1,1.5-Math.abs(4*t-center))));
  return `rgb(${channel(3)}, ${channel(2)}, ${channel(1)})`;
}
if (typeof module !== 'undefined') module.exports = {modelsInDateRange,matchingModels,filterUsageRows,sessionIdentity,summarizeSessions,sessionDetails,sessionMatrix,jetColor};
