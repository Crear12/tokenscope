'use strict';
const $ = id => document.getElementById(id);
const money = n => new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(n);
const compact = n => new Intl.NumberFormat('en-US',{notation:'compact',maximumFractionDigits:1}).format(n);
let data=null, version=-1, selected=new Set(), known=new Set(), csrf='', pending=false, status=null;
const colorMap = new Map();
function color(name){
  if(!colorMap.has(name)) {let hash=2166136261; for(const c of name) hash=Math.imul(hash^c.charCodeAt(0),16777619); colorMap.set(name,`hsl(${(hash>>>0)%360} 48% 49%)`);}
  return colorMap.get(name);
}
function element(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
function svg(tag,attrs,text){const n=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v]of Object.entries(attrs))n.setAttribute(k,v);if(text!==undefined)n.textContent=text;return n;}
function filtered(){return (data?.rows||[]).filter(r=>(!$('from').value||r.date>=$('from').value)&&(!$('through').value||r.date<=$('through').value)&&selected.has(r.model));}
function modelControls(){
  const search=$('search').value.toLowerCase();$('models').replaceChildren();
  for(const model of [...known].sort()){
    if(!model.toLowerCase().includes(search))continue;
    const label=element('label'), input=element('input');input.type='checkbox';input.checked=selected.has(model);input.setAttribute('aria-label',model);
    input.addEventListener('change',()=>{input.checked?selected.add(model):selected.delete(model);render();});
    const swatch=element('span',undefined,'swatch');swatch.style.background=color(model);label.append(input,swatch,document.createTextNode(model));$('models').append(label);
  }
}
function render(){
  const rows=filtered();$('selection').textContent=`Models · ${selected.size} of ${known.size}`;
  $('tokens').textContent=compact(rows.reduce((a,r)=>a+r.tokens,0));
  $('tokens').title=rows.reduce((a,r)=>a+r.tokens,0).toLocaleString('en-US');
  $('cost').textContent=money(rows.reduce((a,r)=>a+Number(r.cost_usd),0));
  $('requests').textContent=rows.reduce((a,r)=>a+r.requests,0).toLocaleString('en-US');
  $('count').textContent=new Set(rows.map(r=>r.model)).size;
  $('empty').hidden=rows.length>0;$('chart-wrap').hidden=!rows.length;$('leaders').replaceChildren();$('tooltip').hidden=true;
  if(!rows.length){$('leaders').append(element('p','No usage matches these filters.'));return;}
  const days=new Map(),months=new Map();
  for(const r of rows){
    if(!days.has(r.date))days.set(r.date,{date:r.date,tokens:0,cost:0,models:new Map()});
    const d=days.get(r.date);d.tokens+=r.tokens;d.cost+=Number(r.cost_usd);d.models.set(r.model,(d.models.get(r.model)||0)+r.tokens);
    const month=r.date.slice(0,7);if(!months.has(month))months.set(month,new Map());const ms=months.get(month);
    const m=ms.get(r.model)||{tokens:0,cost:0};m.tokens+=r.tokens;m.cost+=Number(r.cost_usd);ms.set(r.model,m);
  }
  const leaders=[];
  for(const [month,ms]of [...months].sort()){
    const total=[...ms.values()].reduce((s,r)=>s+r.tokens,0);const max=Math.max(...[...ms.values()].map(r=>r.tokens));
    if(!total)continue;
    for(const [name,r]of ms)if(r.tokens===max){
      leaders.push({month,name,cost:r.cost,share:100*r.tokens/total});
      const box=element('article',undefined,'leader');box.style.borderTopColor=color(name);
      box.append(element('span',month),element('strong',name),element('b',money(r.cost)+' est.'),element('span',`${(100*r.tokens/total).toFixed(1)}% of selected month tokens`));$('leaders').append(box);
    }
  }
  draw([...days.values()].sort((a,b)=>a.date.localeCompare(b.date)),leaders);
}
function draw(days,leaders){
  const chart=$('chart');chart.replaceChildren();const W=Math.max(820,$('chart-wrap').clientWidth),L=65,R=75,B=48;
  const first=Date.parse(days[0].date+'T00:00:00Z'),last=Date.parse(days.at(-1).date+'T00:00:00Z'),span=Math.max(86400000,last-first+86400000);
  const x=d=>L+(Date.parse(d+'T00:00:00Z')-first+43200000)/span*(W-L-R);
  const laneEnds=[];
  const annotations=leaders.map(leader=>{
    const monthDays=days.filter(d=>d.date.startsWith(leader.month));
    const center=(x(monthDays[0].date)+x(monthDays.at(-1).date))/2;
    const nameLines=leader.name.match(/.{1,25}/g)||[leader.name];
    const lines=[leader.month,...nameLines,money(leader.cost)+' est.',leader.share.toFixed(1)+'% of month tokens'];
    const width=Math.max(150,Math.max(...lines.map(s=>s.length))*6.6+18);
    const left=Math.max(L,Math.min(W-R-width,center-width/2));
    let lane=laneEnds.findIndex(end=>end+10<=left);
    if(lane<0)lane=laneEnds.length;
    laneEnds[lane]=left+width;
    return {...leader,lines,width,left,lane};
  });
  const boxHeight=Math.max(0,...annotations.map(a=>a.lines.length*16+16));
  const bandHeight=laneEnds.length*(boxHeight+10);
  const T=bandHeight+32,H=440+bandHeight;
  chart.style.height=H+'px';chart.style.minWidth=W+'px';
  chart.setAttribute('viewBox',`0 0 ${W} ${H}`);
  for(const a of annotations){
    const top=8+a.lane*(boxHeight+10),group=svg('g',{'aria-label':a.lines.join(', '),'data-monthly-label':a.month});
    group.append(svg('rect',{x:a.left,y:top,width:a.width,height:boxHeight,rx:5,fill:'#fff',stroke:color(a.name),'stroke-width':1.6}));
    a.lines.forEach((line,i)=>group.append(svg('text',{x:a.left+a.width/2,y:top+18+i*16,'text-anchor':'middle',fill:'#243341','font-size':12,'font-weight':i>0&&i<=a.lines.length-3?600:400},line)));
    chart.append(group);
  }
  const ymax=Math.max(...days.map(d=>d.tokens),1)*1.08,cmax=Math.max(...days.map(d=>d.cost),1)*1.08;
  const y=n=>H-B-n/ymax*(H-T-B),cy=n=>H-B-n/cmax*(H-T-B);
  for(let i=0;i<=4;i++){let yy=H-B-i/4*(H-T-B);
    chart.append(svg('line',{x1:L,x2:W-R,y1:yy,y2:yy,stroke:'#e2e7ee'}),svg('text',{x:L-10,y:yy+4,'text-anchor':'end',fill:'#627181','font-size':12},compact(ymax*i/4)),svg('text',{x:W-R+10,y:yy+4,fill:'#627181','font-size':12},money(cmax*i/4)));
  }
  chart.append(svg('text',{x:L,y:T-12,fill:'#627181','font-size':12},'Tokens'),svg('text',{x:W-R,y:T-12,'text-anchor':'end',fill:'#627181','font-size':12},'Estimated USD'));
  const width=Math.max(.6,Math.min(42,(W-L-R)/(span/86400000)*.8));
  for(const d of days){let base=0;for(const [name,tokens]of [...d.models].sort()){
    const bar=svg('rect',{x:x(d.date)-width/2,y:y(base+tokens),width,height:tokens/ymax*(H-T-B),fill:color(name),opacity:.7,tabindex:0,'aria-label':`${d.date}, ${name}: ${tokens.toLocaleString()} tokens`});
    const tip=`${d.date}\n${name}\n${tokens.toLocaleString()} tokens\nDay total: ${d.tokens.toLocaleString()} tokens · ${money(d.cost)} est.`;
    const show=()=>{const bounds=bar.getBoundingClientRect(),card=$('tooltip').parentElement.getBoundingClientRect();$('tooltip').textContent=tip;$('tooltip').hidden=false;$('tooltip').style.left=Math.max(5,Math.min(bounds.left-card.left,card.width-335))+'px';$('tooltip').style.top=Math.max(45,bounds.top-card.top-100)+'px';};
    bar.addEventListener('mouseenter',show);bar.addEventListener('focus',show);bar.addEventListener('mouseleave',()=>$('tooltip').hidden=true);bar.addEventListener('blur',()=>$('tooltip').hidden=true);chart.append(bar);base+=tokens;
  }}
  let path='',previous=null;
  for(const d of days){const t=Date.parse(d.date+'T00:00:00Z');path+=(previous!==null&&t-previous===86400000?' L':' M')+x(d.date)+' '+cy(d.cost);previous=t;}
  chart.append(svg('path',{d:path,fill:'none',stroke:'#202b34','stroke-width':2,'pointer-events':'none'}));
  if(days.length===1)chart.append(svg('circle',{cx:x(days[0].date),cy:cy(days[0].cost),r:3,fill:'#202b34'}));
  const labels=[days[0].date];let lastLabel=x(labels[0]);
  for(const d of days.slice(1,-1))if(d.date.endsWith('-01')&&x(d.date)-lastLabel>85&&x(days.at(-1).date)-x(d.date)>85){labels.push(d.date);lastLabel=x(d.date);}
  if(days.length>1&&x(days.at(-1).date)-x(labels[0])>65)labels.push(days.at(-1).date);
  for(const date of labels)chart.append(svg('text',{x:x(date),y:H-18,'text-anchor':'middle',fill:'#627181','font-size':12},date));
}
function installData(next){
  if(!next)return;const allSelected=selected.size===known.size;data=next;
  const names=new Set(data.rows.map(r=>r.model));selected=allSelected?new Set(names):new Set([...selected].filter(m=>names.has(m)));known=names;
  const dates=data.rows.map(r=>r.date).sort();for(const id of ['from','through']){$(id).min=dates[0]||'';$(id).max=dates.at(-1)||'';}
  $('freshness').textContent='Last successful collection: '+new Date(data.generated_at).toLocaleString();
  $('sources').replaceChildren();for(const [name,source]of Object.entries(data.sources))$('sources').append(element('p',`${name} · ${new Date(source.collected_at).toLocaleString()} · ${source.timezone}`));
  $('caveats').replaceChildren(...data.caveats.map(s=>element('li',s)));modelControls();render();
}
async function request(path,body){const r=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Usage-CSRF':csrf},body:JSON.stringify(body)});const value=await r.json();if(!r.ok)throw Error(value.error||'Request failed');return value;}
async function poll(){
  if(pending)return;pending=true;
  try{status=await request('/api/status');csrf=status.csrf;
    if(document.activeElement!==$('interval'))$('interval').value=status.interval;
    $('refresh').disabled=status.refreshing;
    $('status').className=status.error?'error':'';
    $('status').textContent=status.error||(status.refreshing?'Collecting from configured machines… Previous results remain visible.':`Next refresh: ${new Date(status.next_run*1000).toLocaleTimeString()} · host timezone ${status.timezone} · every ${status.interval}s`);
    if(version!==status.version){const next=await request('/api/data');installData(next);version=status.version;if(!next)$('freshness').textContent='No successful collection yet.';}
  }catch(e){$('status').className='error';$('status').textContent='Server unavailable. Showing last loaded results. '+e.message;}finally{pending=false;}
}
for(const id of ['from','through'])$(id).addEventListener('change',render);
$('search').addEventListener('input',modelControls);
$('all').onclick=()=>{selected=new Set(known);modelControls();render();};$('none').onclick=()=>{selected.clear();modelControls();render();};
$('reset').onclick=()=>{$('from').value='';$('through').value='';$('search').value='';selected=new Set(known);modelControls();render();};
async function action(path,body){try{await request(path,body);await poll();}catch(e){$('status').textContent=e.message;$('status').className='error';}}
$('refresh').onclick=()=>action('/api/refresh',{});
$('apply').onclick=()=>{const seconds=Number($('interval').value);if(!Number.isInteger(seconds)||seconds<5||seconds>600){$('status').textContent='Choose an integer from 5 to 600 seconds.';return;}action('/api/interval',{seconds});};
new ResizeObserver(()=>{if(data)render();}).observe($('chart-wrap'));
if(window.TOKEN_SCOPE_DEMO){
  installData(window.TOKEN_SCOPE_DEMO);
  $('freshness').textContent='Interactive demo · entirely synthetic data · January–March 2026';
  $('status').textContent='No database, account, SSH connection, or live collection. All models, tokens and costs below are fictional.';
  $('replay').onclick=()=>{render();$('status').textContent='Replaying the chart reveal. Values are unchanged; this is not live usage.';};
}else{
  poll();setInterval(poll,2000);
}
