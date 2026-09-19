const assert = require('node:assert/strict');
const {filterUsageRows,summarizeSessions} = require('./session_usage.js');
const base = {session_key:'one',host:'workstation',app:'Codex',requests:1,fresh_input_tokens:10,cache_read_tokens:20,cache_creation_tokens:5,output_tokens:15,tokens:50,cost_usd:'0.25'};
const rows = [
  {...base,date:'2026-01-31',model:'a'},
  {...base,date:'2026-02-01',model:'a'},
  {...base,date:'2026-02-02',model:'b'},
  {...base,date:'2026-02-02',model:'a',host:'lab'},
  {...base,date:'2026-02-02',model:'a',app:'Claude Code'},
];
const all = new Set(['a','b']);
let sessions = summarizeSessions(filterUsageRows(rows,'2026-02-01','2026-02-02',all));
assert.equal(sessions.length,3); // same source ID on different machines/apps stays separate
assert.equal(sessions[0].tokens,100);
assert.equal(sessions[0].cost,.5);
assert.equal(sessions[0].first,'2026-02-01');
assert.deepEqual(sessions[0].models,['a','b']);
sessions = summarizeSessions(filterUsageRows(rows,'2026-02-01','2026-02-02',new Set(['b'])));
assert.equal(sessions.length,1);
assert.equal(sessions[0].tokens,50);
assert.equal(sessions[0].first,'2026-02-02');
assert.equal(summarizeSessions(filterUsageRows(rows,'','',new Set())).length,0);
assert.equal(summarizeSessions(filterUsageRows(rows,'2027-01-01','',all)).length,0);
assert.equal(summarizeSessions(filterUsageRows(rows,'','',all))[0].tokens,150);
console.log('Session filtering, multi-day/model aggregation, identity boundaries, and empty/reset checks passed.');
