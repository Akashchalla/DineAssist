// Shared, deterministic table facts. The model explains these; it does not invent them.
export function numberIn(value, fallback, min, max) {
  const n=Number(value); return Number.isFinite(n)?Math.min(max,Math.max(min,n)):fallback;
}
export function secondsFromTimer(value) {
  if(typeof value!=='string'||!/^\d{1,3}:\d{2}(:\d{2})?$/.test(value))return 0;
  return value.split(':').reduce((total,n)=>total*60+Number(n),0);
}
export function tableContext(scene, settings={}) {
  const dining=numberIn(settings.dining,45,10,180), cleaning=numberIn(settings.cleaning,5,1,30);
  const party=Math.round(numberIn(settings.party,2,1,20));
  const tables=(scene.tables||[]).map(t=>{
    const elapsed=secondsFromTimer(t.timer)/60;
    const remaining=Math.max(0,dining-elapsed);
    const wait=t.state==='free'?[0,0]:t.state==='needs_cleaning'?[cleaning,cleaning]:[Math.max(0,Math.floor(remaining-10))+cleaning,Math.ceil(remaining+10)+cleaning];
    return {id:t.id,name:t.name,state:t.state,seats:t.seats,guests:t.customers,greeting:t.greeting,
      elapsedSeconds:Math.round(elapsed*60),waitMinutes:wait};
  });
  const fitting=tables.filter(t=>t.seats>=party).sort((a,b)=>a.waitMinutes[0]-b.waitMinutes[0]);
  return {mode:scene.status==='demo'?'interactive demo':'recorded snapshot',diningMinutes:dining,cleaningMinutes:cleaning,partySize:party,
    caveat:'Illustrative estimates, not learned predictions. Table capacities are demo assumptions. No queue, reservations, meal stage or real departure times are known. Recorded timers are frozen.',
    tables, available:tables.filter(t=>t.state==='free').map(t=>t.name),
    occupied:tables.filter(t=>t.state==='occupied').length,cleaning:tables.filter(t=>t.state==='needs_cleaning').length,
    greetings:tables.filter(t=>t.state==='occupied'&&t.greeting==='overdue').length,nextTable:fitting[0]||null};
}
export function waitLabel(t) {return t.waitMinutes[1]===0?'available now':t.waitMinutes[0]===t.waitMinutes[1]?`about ${t.waitMinutes[0]} min`:`about ${t.waitMinutes[0]}–${t.waitMinutes[1]} min`;}
export function builtInAnswer(question,c) {
  const q=question.toLowerCase(); const tableId=q.match(/(?:table\s*|\bt)(\d+)\b/);
  const assumptions=`Estimate assumes a ${c.diningMinutes}-minute meal, ±10 minutes, plus ${c.cleaningMinutes} minutes for cleaning. It is not a departure prediction; queue and reservations are not included.`;
  if(tableId){const t=c.tables.find(t=>t.id===`table_${Number(tableId[1])}`);if(!t)return 'That table is not in this room. Choose a mapped table number.';
    return `${t.name} is ${t.state==='free'?'available':t.state==='needs_cleaning'?'waiting for cleaning':'occupied'} in this ${c.mode}, with ${t.guests} guest ${t.guests===1?'match':'matches'}. Estimated availability: ${waitLabel(t)}.\n\n${t.state==='occupied'?`Recorded seated time: ${t.elapsedSeconds} ${t.elapsedSeconds===1?'second':'seconds'}. `:''}${assumptions}`;}
  if(/(each|every|all).*(table|estimate)|(table|estimate).*(each|every|all)/.test(q))return `Estimated availability in this ${c.mode}:\n\n${c.tables.map(t=>`${t.name}: ${waitLabel(t)}`).join('\n')}\n\n${assumptions}`;
  if(/\bwait(?:ing)?\b|\bwaittime\b|how long|next table|estimated|estimate/.test(q)){
    if(!c.nextTable)return `No single mapped table fits a party of ${c.partySize} under the demo seat assumptions. Ask the host about joining tables; I cannot estimate that wait.`;
    return `For a party of ${c.partySize}, ${c.nextTable.name} is ${waitLabel(c.nextTable)} in this ${c.mode}.\n\n${assumptions} Seat counts are illustrative, so confirm capacity with the host.`;
  }
  if(/availab|free table|open table/.test(q))return `${c.available.length} tables are available in this ${c.mode}${c.available.length?`: ${c.available.join(', ')}`:'.'}\n\nThis describes the current displayed scenario, not live restaurant availability.`;
  if(/greet|attention|served|waiter/.test(q))return `${c.greetings} occupied tables need a greeting confirmation in this ${c.mode}. A missing confirmation does not prove no service happened. The local app uses manual staff labels or “Record greeting”; it cannot understand conversations.`;
  if(/clean|dirty/.test(q))return `${c.cleaning} tables need cleaning in this ${c.mode}. Guests leaving triggers that state; staff must confirm cleaning before the table becomes available. The camera does not prove a table is clean.`;
  if(/occupied|summary|overview|how busy (is|are)/.test(q))return `Room summary (${c.mode}): ${c.available.length} available, ${c.occupied} occupied, ${c.cleaning} awaiting cleaning, and ${c.greetings} awaiting a greeting confirmation.`;
  if(/how.*work|what.*dineassist|technology|built/.test(q))return 'DineAssist uses manually drawn table zones, YOLO26 person detection (released January 2026) and tracking, and timed state changes. Python/OpenCV process video, FastAPI connects services, SQLite stores events, and Streamlit provides the local dashboard. This public website is an interactive demo; it does not run live cameras.';
  return null;
}
