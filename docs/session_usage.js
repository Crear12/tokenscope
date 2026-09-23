'use strict';
function leaderPeriod(from, through) {
  if (!from && !through) return {unit:'month', monthly:true, label:''};
  const days = from && through ? (Date.parse(through+'T00:00:00Z')-Date.parse(from+'T00:00:00Z'))/86400000+1 : null;
  let unit=days===1?'day':days===7?'week':'range';
  if (from && through && from.slice(0,7)===through.slice(0,7) && from.endsWith('-01')) {
    const next = new Date(Date.parse(through+'T00:00:00Z')+86400000).toISOString().slice(0,10);
    if (next.endsWith('-01')) unit='month';
  }
  return {unit,monthly:false,label:unit==='day'?from:unit==='month'?from.slice(0,7):`${from||'…'} → ${through||'…'}`};
}
function modelsInDateRange(rows, from, through) {
  return new Set(rows.filter(r => (!from || r.date >= from) && (!through || r.date <= through)).map(r => r.model));
}
function matchingModels(models, search) {
  const query = search.toLowerCase();
  return [...models].filter(model => model.toLowerCase().includes(query)).sort();
}
function availableUsageModels(rows, sessionRows, from, through) {
  const names=modelsInDateRange(rows,from,through);
  if(!Array.isArray(sessionRows))return names;
  const valid=new Set(visibleSessionRows(sessionRows).filter(r=>(!from||r.date>=from)&&(!through||r.date<=through)).map(r=>r.model));
  const recorded=new Map();
  for(const r of sessionRows){
    if((from&&r.date<from)||(through&&r.date>through))continue;
    recorded.set(r.model,(recorded.get(r.model)||0)+r.requests);
  }
  const totals=new Map();
  for(const r of rows){
    if((from&&r.date<from)||(through&&r.date>through))continue;
    const total=totals.get(r.model)||{tokens:0,cost:0,requests:0};
    total.tokens+=r.tokens;total.cost+=Number(r.cost_usd);total.requests+=r.requests;
    totals.set(r.model,total);
  }
  for(const [model,total] of totals){
    // Hide only when all recorded requests are accounted for by excluded sessions.
    // Missing session detail or unknown pricing alone must not hide real usage.
    if(/^claude(?:-|$)/i.test(model)&&!valid.has(model)&&total.tokens===0&&total.cost===0&&
       total.requests>0&&recorded.get(model)===total.requests)names.delete(model);
  }
  return names;
}
// Pure functions shared by the live UI, synthetic demo, and regression tests.
function filterUsageRows(rows, from, through, selected) {
  return rows.filter(r => (!from || r.date >= from) && (!through || r.date <= through) && selected.has(r.model));
}
function sessionIdentity(row) {
  return JSON.stringify([row.host,row.app,row.session_key]);
}
// Check the complete snapshot, not a date/model-filtered fragment of a session.
function visibleSessionRows(rows) {
  const rejected = new Set(summarizeSessions(rows)
    .filter(s => s.requests === 1 && s.tokens === 0 && s.cost === 0 &&
      s.models.every(model => /^claude(?:-|$)/i.test(model)))
    .map(sessionIdentity));
  return rows.filter(row => !rejected.has(sessionIdentity(row)));
}
function mergeResponseRates(group,row){
  group.tps_count=(group.tps_count||0)+(row.tps_count||0);
  group.tps_sum=(group.tps_sum||0)+(row.tps_sum||0);
  group.tps_max=Math.max(group.tps_max||0,row.tps_max||0);
  group.tps_avg=group.tps_count?group.tps_sum/group.tps_count:null;
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
    mergeResponseRates(s,r);
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
      mergeResponseRates(group,r);
    }
    return [...groups.values()].map(group => ({...group,models:[...group.models].sort()}));
  };
  return {session,daily:summarize('date').sort((a,b)=>a.value.localeCompare(b.value)),
          models:summarize('model').sort((a,b)=>b.tokens-a.tokens||a.value.localeCompare(b.value))};
}
function sessionMatrix(rows, from, through) {
  const hourly = Boolean(from && from === through);
  const sessions = new Map();
  for (const r of rows) {
    const key = sessionIdentity(r);
    if (!sessions.has(key)) sessions.set(key,{key,title:r.session_title||'',host:r.host,app:r.app,total:0,days:new Map()});
    const s = sessions.get(key);
    if (r.session_title) s.title = r.session_title;
    s.total += r.tokens;
    if (hourly) {
      for (const [hour, tokens] of Object.entries(r.hours || {})) {
        const label = hour + ':00';
        s.days.set(label, (s.days.get(label) || 0) + tokens);
      }
      const missing = r.tokens - Object.values(r.hours || {}).reduce((sum, value) => sum + value, 0);
      if (missing > 0) s.days.set('Unknown hour', (s.days.get('Unknown hour') || 0) + missing);
    } else s.days.set(r.date,(s.days.get(r.date)||0)+r.tokens);
  }
  const ordered = [...sessions.values()].sort((a,b)=>b.total-a.total||a.key.localeCompare(b.key));
  const observed = rows.map(r=>r.date).sort(), dates = [];
  if (hourly && observed.length) {
    dates.push(...Array.from({length:24}, (_, hour) => String(hour).padStart(2,'0') + ':00'));
    if (ordered.some(s => s.days.has('Unknown hour'))) dates.push('Unknown hour');
  } else if (observed.length) {
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
// Compact sampled palettes; interpolate RGB anchors for continuous colors.
const temporalPalettes = {
  viridis:['#440154','#482878','#3e4989','#31688e','#26828e','#1f9e89','#35b779','#6ece58','#b5de2b','#fde725'],
  plasma:['#0d0887','#46039f','#7201a8','#9c179e','#bd3786','#d8576b','#ed7953','#fb9f3a','#fdca26','#f0f921'],
  inferno:['#000004','#1b0c41','#4a0c6b','#781c6d','#a52c60','#cf4446','#ed6925','#fb9b06','#f7d13d','#fcffa4'],
  grayscale:['#000000','#ffffff']
};
function temporalColor(value,min,max,palette='jet') {
  if(palette==='jet')return jetColor(value,min,max);
  const colors=temporalPalettes[palette];
  if(!colors)throw new Error('Unknown temporal palette: '+palette);
  const t=max===min?.5:Math.max(0,Math.min(1,(value-min)/(max-min)));
  const position=t*(colors.length-1),index=Math.min(colors.length-2,Math.floor(position)),fraction=position-index;
  const rgb=hex=>[1,3,5].map(offset=>parseInt(hex.slice(offset,offset+2),16));
  const a=rgb(colors[index]),b=rgb(colors[index+1]);
  return `rgb(${a.map((value,i)=>Math.round(value+(b[i]-value)*fraction)).join(', ')})`;
}
// Interpolate only within consecutive recorded buckets; never bridge missing time.
function temporalRuns(dates, days) {
  const runs = [];
  let run = null;
  dates.forEach((date, index) => {
    if (!days.has(date)) { run = null; return; }
    if (!run || date === 'Unknown hour') { run = []; runs.push(run); }
    run.push({index, tokens:days.get(date)});
    if (date === 'Unknown hour') run = null;
  });
  return runs;
}
if (typeof module !== 'undefined') module.exports = {availableUsageModels,visibleSessionRows,leaderPeriod,modelsInDateRange,matchingModels,filterUsageRows,sessionIdentity,summarizeSessions,sessionDetails,sessionMatrix,jetColor,temporalRuns,temporalColor};
