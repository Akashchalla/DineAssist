import {createApp} from './assets/floor.js';
const $=id=>document.getElementById(id);
let original, scene, selected, floor, activities=[], toastTimer;
const names={free:'Available',occupied:'Occupied',needs_cleaning:'Needs cleaning'};
const host=$('map').attachShadow({mode:'open'});
host.innerHTML='<link rel="stylesheet" href="assets/floor.css"><style>.tf-root.paused .floor-layer{filter:none}.tf-root{min-height:340px}@media(max-width:600px){.tf-root{min-height:290px}.legend{font-size:9px;gap:8px}.who{display:none}}</style><div class="tf-root"></div>';
function toast(message){$('toast').textContent=message;$('toast').style.display='block';clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').style.display='none',3500)}
function actionButton(label,action,primary=false){const b=document.createElement('button');b.textContent=label;b.className=primary?'primary':'';b.onclick=action;return b}
function record(message){activities.unshift(message);activities=activities.slice(0,12);toast(message);render()}
function select(id){selected=id;render()}
function render(){
 const tables=scene.tables;
 $('available').textContent=tables.filter(t=>t.state==='free').length;
 $('occupied').textContent=tables.filter(t=>t.state==='occupied').length;
 $('cleaning').textContent=tables.filter(t=>t.state==='needs_cleaning').length;
 $('greetings').textContent=tables.filter(t=>t.state==='occupied'&&t.greeting==='overdue').length;
 for(const t of tables){t.selected=t.id===selected;t.stateName=names[t.state];t.attention=t.state==='needs_cleaning'||(t.state==='occupied'&&t.greeting==='overdue')}
 floor.update(scene);
 $('table-buttons').replaceChildren(...tables.map(t=>{const b=actionButton(t.label,()=>select(t.id));b.setAttribute('aria-label',`${t.name}, ${t.stateName}`);b.setAttribute('aria-pressed',String(t.selected));return b}));
 const t=tables.find(t=>t.id===selected);$('selected-name').textContent=t.name;
 const details=$('details');details.replaceChildren();
 const badge=document.createElement('div');badge.className=`badge ${t.state}`;badge.textContent=names[t.state];details.append(badge);
 const count=document.createElement('p');count.className='detail-count';count.textContent=`${t.customers} ${t.customers===1?'guest':'guests'}`;details.append(count);
 const note=document.createElement('p');note.className='hint';note.textContent=t.state==='occupied'?(t.greeting==='overdue'?'Greeting needed in this demo scenario.':'Greeting confirmed in this demo scenario.'):t.state==='free'?'Ready for the next party in this demo.':'Guests have left. Confirm cleaning before seating the next party.';details.append(note);
 const actions=document.createElement('div');actions.className='detail-actions';details.append(actions);
 if(t.state==='occupied'){
  if(t.greeting==='overdue')actions.append(actionButton('Record greeting',()=>{t.greeting='greeted';record(`${t.name}: greeting recorded (demo).`)},true));
  actions.append(actionButton('Simulate guests leaving',()=>{t.state='needs_cleaning';t.customers=0;t.greeting=null;t.timer='00:00';record(`${t.name}: ready for cleaning (demo).`)}));
 }else if(t.state==='needs_cleaning')actions.append(actionButton('Confirm cleaned',()=>{t.state='free';t.timer=null;record(`${t.name}: cleaned and available (demo).`)},true));
 else actions.append(actionButton('Seat a party of 2',()=>{t.state='occupied';t.customers=2;t.greeting='overdue';t.timer='05:00';record(`${t.name}: simulated five-minute greeting wait (demo).`)},true));
 const queue=tables.filter(t=>t.attention);$('queue').replaceChildren();
 if(!queue.length){const p=document.createElement('p');p.className='empty';p.textContent='All caught up in this demo.';$('queue').append(p)}
 else for(const t of queue){const b=actionButton(`${t.name} · ${t.state==='needs_cleaning'?'Clean table':'Greeting needed'}`,()=>select(t.id));b.className='queue-item';$('queue').append(b)}
 $('activity').replaceChildren(...(activities.length?activities:['Select a table and try recording a greeting.']).map(text=>{const li=document.createElement('li');li.textContent=text;return li}));
}
for(const b of document.querySelectorAll('[data-panel]'))b.onclick=()=>{
 for(const tab of document.querySelectorAll('[data-panel]')){tab.classList.toggle('active',tab===b);tab.setAttribute('aria-pressed',String(tab===b))}
 for(const panel of document.querySelectorAll('.panel'))panel.classList.toggle('active',panel.id===b.dataset.panel);
 if(b.dataset.panel!=='video')$('recording').pause();
};
$('reset').disabled=true;
try{
 const response=await fetch('demo.json');if(!response.ok)throw new Error('Could not load demo');original=await response.json();
 scene=structuredClone(original);selected=scene.tables[0].id;floor=createApp(host.querySelector('.tf-root'));floor.setTrigger=(_,id)=>select(id);render();
 $('reset').disabled=false;$('reset').onclick=()=>{scene=structuredClone(original);selected=scene.tables[0].id;activities=[];render();toast('Demo reset. Ready to explore again.')};
}catch(error){$('details').textContent='The demo could not load. Please refresh the page.';console.error(error)}
