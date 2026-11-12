const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function styl(root){ (root || document).querySelectorAll('[data-style]').forEach(el => { el.style.cssText = el.dataset.style; el.removeAttribute('data-style'); }); }
const STATIC = window.KEI_STATIC || null;   // a report saved at delivery: the data and the files beside it
function fileUrl(id){ return STATIC ? encodeURI(STATIC.files[id] || '') : '/file/' + encodeURIComponent(id); }
const S = {travel:false, data:null, sel:0, ver:null, onion:true, playing:false, frame:null, hl:null, parts:{}};

function ago(iso){
  if(!iso) return '';
  const s = Math.max(0, (Date.now() - new Date(iso).getTime())/1000);
  if(s < 60) return 'just now';
  if(s < 3600) return Math.round(s/60) + ' min ago';
  return Math.round(s/3600*10)/10 + ' h ago';
}
function span(a, b){
  if(!a || !b) return '';
  const m = Math.round((new Date(b) - new Date(a))/60000);
  return m < 60 ? m + ' min' : (Math.round(m/6)/10) + ' h';
}
function clock(iso){ return iso ? new Date(iso).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'}) : ''; }

/* Frames named in a note: "Frames 9-13 and 26-30", "f0-f2", "frame 11" */
function framesIn(text){
  // Only the frames a note is about: its lead ("Frames 9-13 and 26-30: ...", "f0-f2 and f13-f16 (...): ...").
  const body = String(text).replace(/^critic [\w-]+:\s*/, '');
  const head = /^(?:frames?\s|f\d)/i.test(body) ? body.split(':')[0] : '';
  const out = [];
  const re = /f?(\d{1,3})(?:\s*(?:-|–|to)\s*f?(\d{1,3}))?/gi;
  let m;
  while((m = re.exec(head.replace(/\([^)]*\)/g, '')))) out.push([+m[1], m[2] ? +m[2] : +m[1]]);
  return out;
}
/* Plain words for the history results */
const RESULT = {pass:'passed its gate', fail:'missed its gate', send_back:'sent back by the critics',
  question:'asked you a question', answer:'got your answer', retry:'was let to try again'};

function stageTitle(id){ return (S.data.stages.find(s => s.id === id) || {}).title || id; }

/* ---------- drawing ---------- */
function bbox(drawings){
  let x0=Infinity,y0=Infinity,x1=-Infinity,y1=-Infinity;
  for(const d of drawings){ if(!d) continue;
    for(const l of d.lines || []){ x0=Math.min(x0,l[0],l[2]); x1=Math.max(x1,l[0],l[2]); y0=Math.min(y0,l[1],l[3]); y1=Math.max(y1,l[1],l[3]); } }
  if(!isFinite(x0)) return [-0.6,0,1.2,1.9];
  const pad = 0.12 * Math.max(x1-x0, y1-y0);
  return [x0-pad, y0-pad, (x1-x0)+2*pad, (y1-y0)+2*pad];
}
function figure(d, box, opts={}){
  if(!d) return '';
  const w = opts.w || 2.2;
  const lines = (d.lines||[]).map(l => `<line x1="${l[0]}" y1="${-l[1]}" x2="${l[2]}" y2="${-l[3]}"/>`).join('');
  const col = opts.color || '#22262C';
  let g = `<g stroke="${col}" stroke-width="${w}" stroke-linecap="round" vector-effect="non-scaling-stroke" fill="none">${lines.replace(/<line /g,'<line vector-effect="non-scaling-stroke" ')}</g>`;
  if(opts.extras && d.action && d.action.length){
    const pts = d.action.map(p => `${p[0]},${-p[1]}`).join(' ');
    g += `<polyline points="${pts}" fill="none" stroke="#C2362B" stroke-width="2" stroke-dasharray="6 4" vector-effect="non-scaling-stroke" stroke-linecap="round"/>`;
  }
  if(opts.extras && d.com){
    const [cx, cy] = d.com, r = box[2]*0.016;
    g += `<circle cx="${cx}" cy="${-cy}" r="${r}" fill="#C2362B"/>`;
    g += `<line x1="${cx}" y1="${-cy}" x2="${cx}" y2="${-(box[1]+box[3]*0.06)}" stroke="#C2362B" stroke-width="1" stroke-dasharray="2 3" vector-effect="non-scaling-stroke"/>`;
  }
  return g;
}
function svg(box, inner, ground=true){
  const [x,y,w,h] = box;
  const vb = `${x} ${-(y+h)} ${w} ${h}`;
  const gl = ground ? `<line x1="${x}" y1="0" x2="${x+w}" y2="0" stroke="#9AA4B1" stroke-width="1" vector-effect="non-scaling-stroke"/>` : '';
  return `<svg viewBox="${vb}" preserveAspectRatio="xMidYMid meet" aria-hidden="true">${gl}${inner}</svg>`;
}

/* ---------- versions ---------- */
function versions(){
  const v = S.data.plan_versions || [];
  if(v.length) return v;
  return S.data.plan ? [{n:1, at:null, keys:S.data.plan.keys}] : [];
}
function shownVersion(){
  const v = versions();
  if(!v.length) return null;
  const i = S.ver == null ? v.length-1 : Math.min(S.ver, v.length-1);
  return {cur:v[i], prev:i>0 ? v[i-1] : null, i};
}
function keyAt(ver, f){ return ver ? ver.keys.find(k => k.f === f) : null; }
function changed(k, prev){
  if(!prev) return false;
  const p = keyAt(prev, k.f);
  return !p || JSON.stringify(p.drawing) !== JSON.stringify(k.drawing);
}

/* Critic notes on the newest send-back of the current stage */
function lastNotes(){
  const h = S.data.history || [];
  for(let i=h.length-1;i>=0;i--){
    if(h[i].result === 'send_back') return {at:h[i].at, stage:h[i].stage, items:[...(h[i].misses||[]), ...(h[i].records||[])]};
    if(h[i].result === 'pass' && h[i].stage === S.data.stage) return null;
  }
  return null;
}
function bands(){
  const n = lastNotes();
  if(!n) return [];
  const out = [];
  n.items.forEach((t, i) => framesIn(t).forEach(([a,b]) => out.push({a, b, i})));
  return out;
}

/* ---------- render ---------- */
function renderTrack(){
  const d = S.data;
  $('#track').innerHTML = d.stages.map((s, i) => {
    const now = s.id === d.stage && s.state !== 'done';
    const cls = [s.state, now ? 'now' : ''].join(' ');
    const mark = s.state === 'done' ? '✓' : now ? (s.state === 'working' ? '<span class="pulse">●</span>' : s.state === 'waiting' ? '?' : '!') : '';
    let sub = '';
    if(s.state === 'done') sub = [span(s.start, s.end), s.tries > 1 ? s.tries + ' tries' : ''].filter(Boolean).join(', ');
    else if(now) sub = {working:'working now', waiting:'waiting for you', stopped:'stopped, needs you', paused:'paused, the editor stopped'}[s.state];
    return `<li class="${cls}" ${now ? 'aria-current="step"' : ''}><span class="n">${i+1}</span><span class="t">${esc(s.title)}${sub ? `<small>${esc(sub)}</small>` : ''}</span><span class="mark" aria-hidden="true">${mark}</span></li>`;
  }).join('');
  const cur = $('#track [aria-current]'), ol = $('#track');   // on a phone the stages scroll sideways: show the current one
  if(cur && ol.scrollWidth > ol.clientWidth) ol.scrollLeft = cur.offsetLeft - 16;
}
function renderHead(){
  const d = S.data;
  $('#shotname').textContent = `Shot ${d.shot}` + (d.character ? `, ${d.character.name} with ${String(d.character.control_rig||'').split('/').pop()}` : '');
  $('#request').textContent = d.request ? `“${d.request}”` : '';
  const st = d.stages.find(s => s.id === d.stage) || {};
  const h = d.history || [];
  const last = h.length ? h[h.length-1] : null;
  const words = {working: st.doing, waiting: 'Waiting for your answer', stopped: 'Stopped: Kei needs you', paused: 'Paused: Unreal stopped answering', done: 'Shot delivered'}[st.state] || st.doing;
  const bits = [];
  const tryN = (d.history||[]).filter(x => x.stage === d.stage && ['pass','fail','send_back','question'].includes(x.result)).length;
  if(st.state === 'working') bits.push(`try ${tryN + 1}`);
  const sb = (d.history||[]).filter(x => x.stage === d.stage && x.result === 'send_back').length;
  if(sb) bits.push(`the critics sent it back ${sb === 1 ? 'once' : sb + ' times'}`);
  if(st.start && st.state === 'working') bits.push(`${span(st.start, d.now) || 'under a minute'} on this stage`);
  if(last && !STATIC) bits.push(`last event ${ago(last.at)}`);
  if(STATIC) bits.push(`report saved ${new Date(STATIC.saved).toLocaleDateString()}`);
  $('#now').innerHTML = `<h1>${esc(words)}</h1><p>${esc(bits.join(', '))}</p>`;
}
function renderBanner(){
  const d = S.data;
  if(d.status === 'needs_answer' && d.pending){
    $('#banner').innerHTML = `<div class="banner"><h2>Kei is waiting for your answer</h2>
      <div class="q">${md(d.pending)}</div>
      <div class="cmd"><code>kei answer ${esc(d.shot)} --text "..."</code><button class="btn" id="copy">Copy the command</button></div></div>`;
    $('#copy').onclick = () => { navigator.clipboard?.writeText(`kei answer ${d.shot} --text ""`); $('#copy').textContent = 'Copied'; };
  } else if(d.status === 'needs_human' || d.status === 'paused_machine'){
    const h = d.history || [], last = h[h.length-1] || {};
    $('#banner').innerHTML = `<div class="banner stopped"><h2>${d.status === 'paused_machine' ? 'Paused: Unreal stopped answering' : 'Stopped: Kei needs you'}</h2>
      <div class="q">${(last.misses||[]).map(m => `<p>${esc(m)}</p>`).join('') || 'See the run output below.'}</div></div>`;
  } else $('#banner').innerHTML = '';
}
function md(t){
  return String(t).split('\n').map(l => {
    if(/^#{1,2} /.test(l)) return `<h3>${inline(l.replace(/^#+ /,''))}</h3>`;
    if(/^#{3,} /.test(l)) return `<h4>${inline(l.replace(/^#+ /,''))}</h4>`;
    if(!l.trim()) return '';
    return `<p>${inline(l)}</p>`;
  }).join('');
}
function inline(s){ return esc(s).replace(/\*\*(.+?)\*\*/g,'<b>$1</b>').replace(/`(.+?)`/g,'<code>$1</code>'); }

/* Kei decides whether the shot loops (plan.json "loop"). A loop plays in place or moving; anything else moves and plays once. */
function isLoop(){ return !!(S.data.plan && S.data.plan.loop); }
function moving(){ return !isLoop() || S.travel; }
function rootAt(f){
  const k = (S.data.plan && S.data.plan.travel) || [];
  if(!k.length) return 0;
  if(f <= k[0][0]) return k[0][1];
  for(let i = 1; i < k.length; i++) if(f <= k[i][0]){ const [f0, d0] = k[i-1], [f1, d1] = k[i]; return d0 + (d1 - d0) * (f - f0) / ((f1 - f0) || 1); }
  return k[k.length-1][1];
}
/* Some plans draw each pose where the body is on the floor (the travel is in the drawing), others draw it in place.
   Kei's plan does not say which, so the page measures it: the centre of mass moving forward with the root means the
   travel is drawn in. Then "in place" takes the travel out; otherwise "moving" adds it. */
function travelDrawn(keys){
  const span = rootAt(S.data.plan.frames || 0) - rootAt(0);
  const xs = keys.filter(k => k.drawing && k.drawing.com).map(k => [k.f, k.drawing.com[0]]);
  if(!span || xs.length < 2) return false;
  const a = xs[0], b = xs[xs.length - 1];
  const drawn = (b[1] - a[1]), rootMoved = rootAt(b[0]) - rootAt(a[0]);
  return Math.abs(rootMoved) > 0.1 && drawn / rootMoved > 0.5;
}
function offset(f, keys){
  const travel = rootAt(f) - rootAt(0);
  if(travelDrawn(keys)) return moving() ? 0 : -travel;
  return moving() ? travel : 0;
}
function moved(d, dx){
  if(!d || !dx) return d;
  return {...d, lines:(d.lines||[]).map(l => [l[0]+dx, l[1], l[2]+dx, l[3]]),
          action: d.action && d.action.map(p => [p[0]+dx, p[1]]), com: d.com && [d.com[0]+dx, d.com[1]]};
}
function placeControls(){
  const loop = isLoop(), hasTravel = !!(S.data.plan && S.data.plan.travel && S.data.plan.travel.length);
  $('#placewrap').hidden = !(loop && hasTravel);
  $('#inplace').setAttribute('aria-pressed', String(!S.travel));
  $('#moving').setAttribute('aria-pressed', String(S.travel));
  $('#loopchip').textContent = !S.data.plan ? '' : loop ? 'Loop: Kei planned this to repeat' : 'Plays once: not a loop';
}
function renderTable(){
  const d = S.data, V = shownVersion();
  const sel = $('#ver');
  const vs = versions();
  sel.innerHTML = vs.map((v, i) => `<option value="${i}" ${V && V.i === i ? 'selected' : ''}>${i === vs.length-1 ? 'Latest, ' : ''}try ${v.n}${v.at ? ', ' + clock(v.at) : ''}</option>`).join('');
  sel.disabled = vs.length < 2;
  $('#onion').disabled = !(V && V.prev);
  if(!V || !V.cur.keys.length){
    $('#glass').innerHTML = `<p class="empty">No key poses yet. They appear here as soon as Kei draws its plan, at the Plan stage.</p>`;
    $('#detail').innerHTML = `<p class="fn">Waiting for the plan</p><p class="note">The stages before the plan read the request, the rig, the weight and the references.</p>`;
    $('#ruler').innerHTML = ''; $('#strip').innerHTML = '';
    return;
  }
  const keys = V.cur.keys;
  S.sel = Math.min(S.sel, keys.length-1);
  placeControls();
  const pk = V.prev ? V.prev.keys : [];
  const box = bbox([...keys.map(k => moved(k.drawing, offset(k.f, keys))), ...pk.map(k => moved(k.drawing, offset(k.f, pk)))]);
  const span = Math.abs(offset(S.data.plan.frames || 0, keys) - offset(0, keys)) > 0.05;
  const tableBox = box;
  const showKey = S.playing && S.frame != null ? keys.filter(k => k.f <= S.frame).pop() || keys[0] : keys[S.sel];
  const prevK = V.prev ? keyAt(V.prev, showKey.f) : null;
  const shown = moved(showKey.drawing, offset(showKey.f, keys));     // stepped: a pose holds its place until the next key
  const onion = S.onion && prevK && !S.playing ? figure(moved(prevK.drawing, offset(prevK.f, pk)), box, {color:'#2F6FD0', w:2}) : '';
  const ticks = span ? Array.from({length: Math.floor(box[2] / 0.25) + 2}, (_, i) => { const x = Math.ceil(box[0] / 0.25) * 0.25 + i * 0.25; return `<line x1="${x}" y1="0" x2="${x}" y2="0.03" stroke="#9AA4B1" stroke-width="1" vector-effect="non-scaling-stroke"/>`; }).join('') : '';
  const fno = S.playing && S.frame != null ? S.frame : showKey.f;
  $('#glass').innerHTML = `<span class="fno">${fno}</span>
    <div class="legend"><span class="loa">Red dashes: line of action</span><span class="loa">Red dot: centre of mass</span>${onion ? '<span class="on">Blue: the previous try</span>' : ''}</div>
    ${svg(tableBox, ticks + `<g opacity=".55">${onion}</g>` + figure(shown, box, {extras:true, w:2.6}))}`;
  renderDetail(showKey, V, box);
  renderRuler(keys, V);
  renderStrip(keys, V);
}
function renderDetail(k, V, box){
  const prevK = V.prev ? keyAt(V.prev, k.f) : null;
  const hits = bands().filter(b => k.f >= b.a - 1 && k.f <= b.b + 1);
  const notes = lastNotes();
  const viewFig = (name, dr) => {
    if(!dr) return '';
    const all = V.cur.keys.map(x => x.views && x.views[name]).filter(Boolean);
    return `<figure><figcaption>${name === 'front' ? 'Front' : name === 'top' ? 'Top' : name}</figcaption>${svg(bbox(all), figure(dr, bbox(all), {extras:true, w:2}), name !== 'top')}</figure>`;
  };
  const views = Object.entries(k.views || {}).map(([n, dr]) => viewFig(n, dr)).join('');
  $('#detail').innerHTML = `
    <div class="meta"><span class="chip key">Frame ${k.f}</span><span class="chip">${esc(k.kind)}</span>
      ${changed(k, V.prev) ? '<span class="chip changed">Redrawn in this try</span>' : V.prev ? '<span class="chip">Same as the try before</span>' : ''}
      ${hits.length ? `<span class="chip hit">${hits.length} critic note${hits.length>1?'s':''} near here</span>` : ''}</div>
    <p class="fn">${esc(k.function)}</p>
    <p class="note">${esc(k.note || '')}</p>
    ${views ? `<div class="views">${views}</div>` : ''}
    ${hits.length && notes ? `<div class="hits"><h4>The critics on these frames</h4>${[...new Set(hits.map(h => h.i))].map(i => { const m = /^critic ([\w-]+):\s*/.exec(notes.items[i]); return `<p><b>${m ? (m[1] === 'codex' ? 'Codex critic' : 'Claude critic') : 'The gate'}:</b> ${esc(m ? notes.items[i].slice(m[0].length) : notes.items[i])}</p>`; }).join('')}</div>` : ''}`;
}
function renderRuler(keys, V){
  const N = S.data.plan.frames || Math.max(...keys.map(k => k.f)) + 1;
  const pct = f => (f / N * 100) + '%';
  let h = '<div class="base"></div>';
  for(let f = 0; f <= N; f++){
    h += `<div class="tick ${f % 5 === 0 ? 'five' : ''}" data-style="left:${pct(f)}"></div>`;
    if(f % 5 === 0 || f === N) h += `<div class="num" data-style="left:${pct(f)}">${f}</div>`;
  }
  bands().forEach(b => { b = {...b, a: Math.max(0, Math.min(b.a, N)), b: Math.max(0, Math.min(b.b, N - 1))};
    h += `<div class="band" title="A critic flagged frames ${b.a} to ${b.b}" data-style="left:${pct(b.a)};width:calc(${pct(b.b - b.a + 1)})" data-f="${b.a}"></div>`;
  });
  keys.forEach((k, i) => {
    const cls = ['key','extreme','breakdown'].includes(k.kind) ? k.kind : 'breakdown';
    const sel = !S.playing && i === S.sel ? 'sel' : '';
    h += `<button class="k ${cls} ${sel}" data-style="left:${pct(k.f)}" data-i="${i}" aria-label="Frame ${k.f}, ${esc(k.function)}">${k.f}${changed(k, V.prev) ? '<i class="dot"></i>' : ''}</button>`;
  });
  if(S.playing && S.frame != null) h += `<div class="head" data-style="left:${pct(S.frame)}"></div>`;
  $('#ruler').innerHTML = h;
  $('#ruler').querySelectorAll('.k').forEach(b => b.onclick = () => selectKey(+b.dataset.i));
  $('#ruler').querySelectorAll('.band').forEach(b => b.onclick = () => jumpToFrame(+b.dataset.f));
}
function renderStrip(keys, V){
  // thumbnails always show the pose in place, so each one fills its card
  const drawn = travelDrawn(keys);
  const still = k => moved(k.drawing, drawn ? -(rootAt(k.f) - rootAt(0)) : 0);
  const box = bbox(keys.map(still));
  $('#strip').innerHTML = keys.map((k, i) => `<button class="${i === S.sel && !S.playing ? 'sel' : ''}" data-i="${i}" aria-label="Frame ${k.f}, ${esc(k.function)}">
    ${changed(k, V.prev) ? '<i class="dot" title="Redrawn in this try"></i>' : ''}
    ${svg(box, figure(still(k), box, {w:1.6}))}<span>${k.f}, <b>${esc(k.function)}</b></span></button>`).join('');
  $('#strip').querySelectorAll('button').forEach(b => b.onclick = () => selectKey(+b.dataset.i));
}
function selectKey(i){ stop(); S.sel = i; renderTable(); styl(); }
function jumpToFrame(f){
  const V = shownVersion(); if(!V) return;
  let best = 0, bd = 1e9;
  V.cur.keys.forEach((k, i) => { const dd = Math.abs(k.f - f); if(dd < bd){ bd = dd; best = i; } });
  selectKey(best);
  $('.lighttable').scrollIntoView({behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block:'start'});
}

function renderNotes(){
  const n = lastNotes();
  if(!n){ $('#notes').innerHTML = `<div class="critic"><h3>No open notes</h3><ol class="plain"><li>The critics have not sent the current stage back.</li></ol></div>`; return; }
  const groups = {};
  n.items.forEach((t, i) => {
    const m = /^critic ([\w-]+):\s*/.exec(t);
    const who = m ? m[1] : 'The gate';
    (groups[who] = groups[who] || []).push({t: m ? t.slice(m[0].length) : t, i});
  });
  $('#notes-lead').textContent = `${stageTitle(n.stage)} was sent back ${ago(n.at)}. Click a frame to see it on the table.`;
  $('#notes').innerHTML = Object.entries(groups).map(([who, items]) => `<div class="critic"><h3>${esc(who === 'claude-critic' ? 'Claude critic' : who === 'codex' ? 'Codex critic' : who)}<span>${items.length} note${items.length>1?'s':''}</span></h3><ol>${
    items.map(({t}) => {
      const fr = framesIn(t).map(([a,b]) => `<button class="chip hit fr" data-f="${a}">${a === b ? 'f' + a : 'f' + a + ' to ' + b}</button>`).join('');
      return `<li>${fr}${esc(t)}</li>`;
    }).join('')}</ol></div>`).join('');
  $('#notes').querySelectorAll('.fr').forEach(b => b.onclick = () => jumpToFrame(+b.dataset.f));
}
function renderFeed(){
  const h = [...(S.data.history || [])].reverse();
  $('#feed').innerHTML = h.map(e => {
    const items = [...(e.misses||[]), ...(e.records||[])];
    let why = '';
    if(e.result === 'question' || e.result === 'answer'){
      const a = (S.data.answers || []).find(x => x.at === e.at);
      if(a) why = `<p class="why">You answered: ${esc(a.answer.length > 220 ? a.answer.slice(0, 220) + '…' : a.answer)}</p>`;
    }
    if(items.length) why += items.length > 2
      ? `<details><summary>${items.length} notes</summary><ul class="why">${items.map(x => `<li>${esc(x)}</li>`).join('')}</ul></details>`
      : `<ul class="why">${items.map(x => `<li>${esc(x)}</li>`).join('')}</ul>`;
    return `<li class="c-${esc(e.result)}"><div class="when">${clock(e.at)}, ${ago(e.at)}</div><div class="what">${esc(stageTitle(e.stage))} ${esc(RESULT[e.result] || e.result)}${e.attempt ? ` (try ${e.attempt})` : ''}</div>${why}</li>`;
  }).join('') || '<li>Nothing yet.</li>';
}
function renderRefs(){
  const d = S.data;
  $('#facts').innerHTML = Object.entries(d.facts || {}).map(([k, v]) => `<div><b>${esc(k)}</b>${esc(v)}</div>`).join('');
  const call = c => c.startsWith('keep') ? 'keep' : c.startsWith('flag') ? 'flag' : c.startsWith('reject') ? 'reject' : '';
  const word = {keep:'Kept', flag:'Used with care', reject:'Rejected'};
  const tier = {R:'Research', B:'Craft reference', A:'Asset', C:'Own work'};
  $('#refs').innerHTML = (d.refs || []).map(r => {
    const c = call(r.call);
    const [label, ...rest] = r.verdict.split(':');
    const all = [r.gives, r.checks, r.verdict].join(' ');
    const unchecked = (all.match(/\(unchecked\)/gi) || []).length;
    const memory = /from memory|not re-?read|until re-?read/i.test(all);
    const mark = s => esc(s).replace(/\(unchecked\)/gi, '<mark class="unchk">unchecked</mark>');
    const warn = unchecked ? `<span class="chip unchk-chip" title="Numbers Kei did not read in the source during this shot">${unchecked} unchecked number${unchecked > 1 ? 's' : ''}</span>`
      : memory ? '<span class="chip unchk-chip" title="Kei says these values come from memory">Numbers from memory, unchecked</span>' : '';
    return `<article class="ref"><div class="head"><span class="tier" title="${esc(tier[r.tier] || r.tier)}">${esc(r.tier)}</span><h3>${esc(r.ref.replace(/^\d+\.\s*/, ''))}</h3></div>
      <div class="calls"><span class="chip call ${c}">${esc(word[c] || label)}</span>${warn}</div>
      <p>${esc(rest.join(':').trim() || r.verdict)}</p>
      <details${unchecked ? ' open' : ''}><summary>What it gives and how it was checked</summary><p>${mark(r.gives)}</p><p>${mark(r.checks)}</p></details></article>`;
  }).join('') || '<p class="lead">No references yet. They appear at the References stage.</p>';
}
function renderPasses(){
  const ps = S.data.passes || [];
  if(!ps.length){ $('#passes').innerHTML = '<p class="lead">No pass yet. The first one, the blocking, is keyed in Unreal and rendered after the plan is approved.</p>'; return; }
  $('#passes').innerHTML = [...ps].reverse().map(p => `<div class="pass"><h3>${esc(p.name.replace(/^p(\d+)$/, 'Pass $1').replace(/^blocking$/, 'Blocking'))}</h3>
    ${p.videos.map(v => `<video src="${fileUrl(v.id)}" controls loop muted playsinline preload="metadata"></video>`).join('')}
    ${p.frames.length ? `<div class="filmstrip">${p.frames.map(f => `<img loading="lazy" src="${fileUrl(f.id)}" alt="Frame ${esc(f.name)}" data-zoom="${esc(f.id)}" data-cap="${esc(f.name)}">`).join('')}</div>` : ''}
</div>`).join('');
  bindZoom($('#passes'));
}
function renderGallery(){
  const imgs = S.data.images || [];
  $('#gallery').innerHTML = imgs.map(i => `<figure data-zoom="${esc(i.id)}" data-cap="${esc(i.name)}"><img loading="lazy" src="${fileUrl(i.id)}${STATIC ? '' : '?v=' + Math.round(i.mtime)}" alt="${esc(i.name)}"><figcaption>${esc(i.name)}<span>${esc(i.group)}</span></figcaption></figure>`).join('') || '<p class="lead">No sheets yet.</p>';
  bindZoom($('#gallery'));
}
function bindZoom(root){
  root.querySelectorAll('[data-zoom]').forEach(el => el.onclick = () => {
    $('#zoom-img').src = fileUrl(el.dataset.zoom) + (STATIC ? '' : '?t=' + Date.now());
    $('#zoom-cap').textContent = el.dataset.cap || '';
    $('#zoom').showModal();
  });
}
$('#zoom-close').onclick = () => $('#zoom').close();
$('#zoom').onclick = e => { if(e.target.id === 'zoom') $('#zoom').close(); };

/* Re-render only the parts whose data changed, so playback and scroll stay put */
function render(){
  const d = S.data;
  const parts = {
    track: [d.stages, d.stage, d.status], head: [d.stage, d.status, d.history.length, d.character, d.request],
    banner: [d.status, d.pending], table: [d.plan, d.plan_versions, d.history.length],
    notes: [d.history.length], feed: [d.history, d.answers], refs: [d.refs, d.facts],
    passes: [d.passes], gallery: [d.images]};
  const fns = {track:renderTrack, head:renderHead, banner:renderBanner, table:renderTable, notes:renderNotes,
    feed:renderFeed, refs:renderRefs, passes:renderPasses, gallery:renderGallery, log:() => { $('#log').textContent = d.log.join('\n'); }};
  for(const [k, v] of Object.entries(parts)){
    const j = JSON.stringify(v);
    if(S.parts[k] !== j){ S.parts[k] = j; fns[k](); }
  }
  styl();
}

/* Play: each key held to the next one (stepped, as blocking plays), at the shot's frame rate times the speed */
const ICON_PLAY = '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M4 2.5v11l9.5-5.5z" fill="currentColor"/></svg>';
const ICON_PAUSE = '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M3.5 2.5h3v11h-3zM9.5 2.5h3v11h-3z" fill="currentColor"/></svg>';
let timer = null;
function playButton(){
  $('#play').innerHTML = S.playing ? ICON_PAUSE + '<span>Pause</span>' : ICON_PLAY + '<span>Play</span>';
  $('#play').setAttribute('aria-pressed', String(S.playing));
}
function play(){
  const V = shownVersion(); if(!V || !V.cur.keys.length) return;
  const N = S.data.plan.frames, fps = (S.data.plan.fps || 30) * (+$('#speed').value || 1);
  S.playing = true; S.frame = V.cur.keys[S.sel] ? V.cur.keys[S.sel].f : 0;
  playButton();
  if(!isLoop() && S.frame >= N - 1) S.frame = 0;          // a shot that plays once starts over from the top
  timer = setInterval(() => {
    if(!isLoop() && S.frame >= N - 1){ stop(); return; }   // plays once and stops on its last frame
    S.frame = (S.frame + 1) % N; renderTable(); styl();
  }, 1000 / fps);
  renderTable(); styl();
}
function stop(){
  if(timer) clearInterval(timer); timer = null;
  if(S.playing){
    const V = shownVersion();
    if(V && S.frame != null){ let i = 0; V.cur.keys.forEach((k, j) => { if(k.f <= S.frame) i = j; }); S.sel = i; }  // pause on the key shown
    S.playing = false; S.frame = null; playButton(); renderTable(); styl();
  }
}
$('#inplace').onclick = () => { S.travel = false; renderTable(); styl(); };
$('#moving').onclick = () => { S.travel = true; renderTable(); styl(); };
$('#speed').onchange = () => { if(S.playing){ stop(); play(); } };
playButton();
$('#play').onclick = () => S.playing ? stop() : play();
$('#prev').onclick = () => { const V = shownVersion(); if(V) selectKey((S.sel - 1 + V.cur.keys.length) % V.cur.keys.length); };
$('#next').onclick = () => { const V = shownVersion(); if(V) selectKey((S.sel + 1) % V.cur.keys.length); };
$('#onion').onclick = () => { S.onion = !S.onion; $('#onion').setAttribute('aria-pressed', String(S.onion)); renderTable(); styl(); };
$('#ver').onchange = e => { const v = versions(); S.ver = +e.target.value === v.length - 1 ? null : +e.target.value; renderTable(); styl(); };
document.addEventListener('keydown', e => {
  if(e.target.closest('input,textarea,select') || $('#zoom').open) return;
  if(e.key === 'ArrowLeft'){ $('#prev').click(); e.preventDefault(); }
  if(e.key === 'ArrowRight'){ $('#next').click(); e.preventDefault(); }
  if(e.key === ' '){ $('#play').click(); e.preventDefault(); }
});

/* Live link: the page asks every second; the server answers "same" until something in the shot changed */
let lastLoad = null, version = null, failures = 0;
async function load(){
  try{
    const r = await fetch('/api/live' + (version == null ? '' : '?v=' + version), {cache:'no-store', credentials:'same-origin'});
    if(!r.ok) throw new Error(String(r.status));
    const d = await r.json();
    lastLoad = Date.now(); failures = 0;
    if(!d.same){ version = d.version; S.data = d; render(); }
    setLive(true);
  }catch(e){ failures++; if(failures > 2) setLive(false); }
  setTimeout(load, document.hidden ? 4000 : 1000);
}
function setLive(on){
  const el = $('#live');
  el.classList.toggle('off', !on);
  el.querySelector('span').textContent = on ? 'Live' : 'Kei stopped serving this page. Run the shot again to bring it back.';
}
setInterval(() => { if(S.data && !STATIC){ renderHead(); } }, 20000);
if(STATIC){
  S.data = STATIC.snapshot; render();
  const el = $('#live'); el.querySelector('span').textContent = 'Saved at delivery, ' + new Date(STATIC.saved).toLocaleString();
}else load();
