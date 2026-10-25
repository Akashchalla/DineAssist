import {tableContext,builtInAnswer,waitLabel} from './assistant-data.js';
export function initAssistant(getScene){
 const $=id=>document.getElementById(id);let history=[],busy=false;
 const welcome=$('messages').innerHTML;
 const settings=()=>({party:$('party-size').value,dining:$('dining-minutes').value,cleaning:$('cleaning-minutes').value});
 function outlook(){const scene=getScene();if(!scene)return;const c=tableContext(scene,settings());
  $('assistant-summary').textContent=`${c.available.length} available · ${c.occupied} occupied · ${c.greetings} greetings needed`;
  $('wait-outlook').replaceChildren(...c.tables.map(t=>{const row=document.createElement('div');const name=document.createElement('span');name.textContent=t.name;const wait=document.createElement('b');wait.textContent=waitLabel(t);if(t.state==='free')wait.className='available';row.append(name,wait);return row}));
 }
 function message(role,text,engine=''){const item=document.createElement('article');item.className=`message ${role}-message`;const author=document.createElement('span');author.className='message-author';author.textContent=role==='user'?'You':'DineAssist';const p=document.createElement('p');p.textContent=text;item.append(author,p);if(engine){const small=document.createElement('small');small.textContent=engine;item.append(small)}$('messages').append(item);$('messages').scrollTop=$('messages').scrollHeight;return item}
 function setBusy(value){busy=value;$('send-chat').disabled=value;$('clear-chat').disabled=value;$('send-chat').textContent=value?'Thinking…':'Send ↑';for(const b of document.querySelectorAll('[data-question]'))b.disabled=value}
 async function send(text){
  const scene=getScene();if(busy||!text.trim())return;if(!scene){message('assistant','The table map is still loading. Please try again.');return}
  const party=text.match(/(?:party\s+of|for)\s+(\d+)\s*(?:people|guests|persons)?/i);if(party)$('party-size').value=Math.min(20,Math.max(1,Number(party[1])));
  outlook();const input={message:text.trim(),tables:scene.tables,mode:scene.status==='demo'?'demo':'recorded',settings:settings(),history:history.slice(-6)};
  const c=tableContext(scene,input.settings);message('user',input.message);$('chat-input').value='';setBusy(true);const pending=message('assistant','Checking the table view…');
  try{
   const response=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(input),signal:AbortSignal.timeout(55000)});
   let data;try{data=await response.json()}catch{throw new Error('The AI connection is unavailable in this preview.')}
   if(!response.ok)throw new Error(data.error||'The assistant is temporarily unavailable.');
   pending.remove();message('assistant',data.answer,`${data.engine} · current ${c.mode}`);history.push({role:'user',content:input.message},{role:'assistant',content:data.answer});history=history.slice(-6);
  }catch(error){pending.remove();const fallback=builtInAnswer(input.message,c);message('assistant',fallback||`${error.name==='TimeoutError'?'The AI response took too long. Please try again.':error.message} You can still ask about available tables or wait estimates.`,fallback?'Table data · local fallback':'Connection notice');}
  finally{setBusy(false);$('chat-input').focus()}
 }
 $('chat-form').onsubmit=e=>{e.preventDefault();send($('chat-input').value)};
 $('chat-input').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();send($('chat-input').value)}};
 for(const b of document.querySelectorAll('[data-question]'))b.onclick=()=>send(b.dataset.question);
 for(const id of ['party-size','dining-minutes','cleaning-minutes'])$(id).addEventListener('input',outlook);
 $('clear-chat').onclick=()=>{history=[];$('messages').innerHTML=welcome};
 $('chat-launcher').onclick=()=>{document.querySelector('[data-panel="assistant"]').click();$('assistant').scrollIntoView({behavior:'smooth',block:'start'});$('chat-input').focus({preventScroll:true})};
 document.addEventListener('dineassist:updated',outlook);
 fetch('/api/chat').then(r=>r.ok?r.json():null).then(data=>{$('assistant-status').textContent=data?.configured?'✦ Twinly connected':'Table helper · AI not connected'}).catch(()=>{$('assistant-status').textContent='Table helper · offline preview'});
}
