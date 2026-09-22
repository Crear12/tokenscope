const assert = require('node:assert/strict');
const {temporalColor} = require('./session_usage.js');
assert.equal(temporalColor(0,0,100,'viridis'),'rgb(68, 1, 84)');
assert.equal(temporalColor(100,0,100,'viridis'),'rgb(253, 231, 37)');
assert.equal(temporalColor(50,0,100,'grayscale'),'rgb(128, 128, 128)');
assert.equal(temporalColor(5,5,5,'grayscale'),'rgb(128, 128, 128)');
assert.equal(temporalColor(-1,0,100,'plasma'),temporalColor(0,0,100,'plasma'));
assert.equal(temporalColor(101,0,100,'inferno'),temporalColor(100,0,100,'inferno'));
assert.equal(temporalColor(0,0,100),'rgb(0, 0, 128)');
assert.throws(()=>temporalColor(0,0,100,'missing'),/Unknown temporal palette/);
const {temporalRuns} = require('./session_usage.js');
const runs=temporalRuns(['a','b','c','d','Unknown hour'],new Map([['a',10],['b',30],['d',0],['Unknown hour',9]]));
assert.deepEqual(runs,[[{index:0,tokens:10},{index:1,tokens:30}],[{index:3,tokens:0}],[{index:4,tokens:9}]]);
assert.deepEqual(temporalRuns(['a'],new Map()),[]);
assert.equal(runs.flat().reduce((sum,p)=>sum+p.tokens,0),49);
const {matchingModels} = require('./session_usage.js');
const modelNames = new Set(['Atlas Code','Cedar Think','Orbit Local']);
assert.deepEqual(matchingModels(modelNames,'CODE'), ['Atlas Code']);
assert.deepEqual(matchingModels(modelNames,''), ['Atlas Code','Cedar Think','Orbit Local']);
assert.deepEqual(matchingModels(modelNames,'not found'), []);
assert.deepEqual(matchingModels(modelNames,'o'), ['Atlas Code','Orbit Local']);
const {filterUsageRows,summarizeSessions,sessionDetails,sessionMatrix,jetColor} = require('./session_usage.js');
const base = {session_key:'one',host:'workstation',app:'Codex',requests:1,fresh_input_tokens:10,cache_read_tokens:20,cache_creation_tokens:5,output_tokens:15,tokens:50,cost_usd:'0.25'};
const rows = [
  {...base,date:'2026-01-31',model:'a'},
  {...base,date:'2026-02-01',model:'a'},
  {...base,date:'2026-02-02',model:'b'},
  {...base,date:'2026-02-02',model:'a',host:'lab'},
  {...base,date:'2026-02-02',model:'a',app:'Claude Code'},
];
const all = new Set(['a','b']);
const {modelsInDateRange} = require('./session_usage.js');
assert.deepEqual([...modelsInDateRange(rows,'','')], ['a','b']);
assert.deepEqual([...modelsInDateRange(rows,'2026-02-01','2026-02-01')], ['a']);
assert.deepEqual([...modelsInDateRange(rows,'','2026-02-01')], ['a']);
assert.deepEqual([...modelsInDateRange(rows,'2026-02-02','')], ['b','a']);
assert.equal(modelsInDateRange(rows,'2027-01-01','').size,0);
assert.equal(modelsInDateRange(rows,'2026-02-02','2026-02-01').size,0);
assert.deepEqual(matchingModels(modelsInDateRange(rows,'2026-02-01','2026-02-01'),'b'), []);
assert.deepEqual(matchingModels(modelsInDateRange(rows,'2026-02-01','2026-02-02'),'B'), ['b']);
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
const detail = sessionDetails(rows, JSON.stringify(['workstation','Codex','one']));
assert.equal(detail.session.tokens,150);
assert.equal(detail.daily.length,3);
assert.equal(detail.daily[1].tokens,50);
assert.equal(detail.models.length,2);
assert.equal(detail.models[0].value,'a');
assert.equal(detail.models[0].tokens,100);
assert.deepEqual(sessionDetails(rows, JSON.stringify(['missing','Codex','one'])),{session:null,daily:[],models:[]});
console.log('Session drill-down details aggregate only the selected machine/app/session identity.');
const matrixRows=[{...base,date:'2026-02-01',model:'a',session_title:'Same title'},
  {...base,date:'2026-02-01',model:'b',session_title:'Same title'},
  {...base,date:'2026-02-03',model:'a',session_key:'two',session_title:'Same title',tokens:10}];
let matrix=sessionMatrix(matrixRows,'2026-02-01','2026-02-03');
assert.equal(matrix.sessions.length,2);
assert.deepEqual(matrix.dates,['2026-02-01','2026-02-02','2026-02-03']);
assert.equal(matrix.sessions[0].days.get('2026-02-01'),100);
assert.equal(matrix.sessions[0].days.has('2026-02-02'),false);
assert.equal(matrix.min,10);assert.equal(matrix.max,100);
matrix=sessionMatrix(filterUsageRows(matrixRows,'2026-02-01','2026-02-01',new Set(['a'])),'2026-02-01','2026-02-01');
assert.equal(matrix.sessions.length,1);assert.equal(matrix.min,50);assert.equal(matrix.max,50);
assert.equal(matrix.dates.length,25); // old snapshots explicitly retain unknown-time usage
assert.equal(matrix.sessions[0].days.get('Unknown hour'),50);
const hourly = sessionMatrix([{...base,date:'2026-02-01',hours:{'09':20,'23':30}}], '2026-02-01','2026-02-01');
assert.equal(hourly.dates.length,24);
assert.equal(hourly.sessions[0].days.get('09:00'),20);
assert.equal(hourly.sessions[0].days.get('23:00'),30);
assert.equal(hourly.min,20);assert.equal(hourly.max,30);
assert.equal([...hourly.sessions[0].days.values()].reduce((a,b)=>a+b,0),50);
assert.equal(jetColor(50,50,50),'rgb(128, 255, 128)');
assert.equal(jetColor(0,0,100),'rgb(0, 0, 128)');
assert.equal(jetColor(100,0,100),'rgb(128, 0, 0)');
assert.deepEqual(sessionMatrix([],'',''),{sessions:[],dates:[],min:0,max:0});
console.log('Session matrix totals, date gaps, duplicate titles, adaptive filtering, empty and constant scales passed.');
