'use strict';
const $ = s => document.querySelector(s);
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icon = name => window.feather.icons[name].toSvg();
const moodIcons = {'开心':'smile','松弛':'sun','平静':'coffee','疲惫':'moon','低落':'cloud','焦虑':'wind'};
const state = {user:null,csrf:'',entries:[],overview:{days:[],tags:[]},offset:0,total:0,date:'',view:'diary',editing:null,mood:'平静',dirty:false,register:false,busy:false};
let month = new Date(); month.setDate(1);
let toastTimer, searchTimer, requestSerial = 0;
const dateISO = d => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
const today = () => dateISO(new Date());
const parseDate = s => new Date(s+'T12:00:00');
const dayBefore = count => {const d=new Date();d.setDate(d.getDate()-count);return dateISO(d);};
const dateLabel = s => parseDate(s).toLocaleDateString(AppI18N.locale,{year:'numeric',month:'long',day:'numeric'});
const weekday = s => parseDate(s).toLocaleDateString(AppI18N.locale,{weekday:'long'});
function toast(message){$('#toast').textContent=message;$('#toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').hidden=true,4000);}
async function api(path, options={}){
  let response;
  try{response=await fetch('/api'+path,{...options,headers:{'Content-Type':'application/json','X-CSRF-Token':state.csrf,...options.headers},body:options.body?JSON.stringify(options.body):undefined});}catch(error){throw new Error('连接失败，请检查本地服务后重试；编辑内容仍保留在当前窗口。');}
  let result;try{result=await response.json();}catch(error){throw new Error('服务响应异常，请稍后重试；编辑内容仍保留在当前窗口。');}
  if(!response.ok){if(response.status===401 && !['/login','/register'].includes(path)){state.user=null;updateProfile();}throw new Error(result.error||'暂时没有完成，请稍后重试');}
  if(result.csrf)state.csrf=result.csrf;
  return result;
}
function updateProfile(populate=true){if(!state.user){RelaxationPlayer.stop();GameRoom.leave();closeLedgerReports();ledgerRequest++;}document.body.classList.remove('session-loading');document.body.classList.toggle('signed-out',!state.user);$('#profile-name').textContent=state.user?state.user.nickname:'登录 / 注册';$('#auth-close').hidden=!state.user;if(state.user){document.querySelector('.profile-button .avatar img').src=state.user.avatar_url;if(populate){setLanguage(state.user.language);populateProfile();}}else{$('#period-result').innerHTML='';openAuth();}}
function requireUser(){if(state.user)return true;openAuth();return false;}
function openAuth(){state.register=false;updateAuth();if(!$('#auth-dialog').open)$('#auth-dialog').showModal();}
function updateAuth(){$('#auth-title').textContent=state.register?'拥有自己的小角落':'回到你的小角落';$('#auth-confirm-wrap').hidden=!state.register;$('#auth-confirm-wrap input').required=state.register;$('#auth-submit').textContent=state.register?'注册':'登录';$('#auth-switch').textContent=state.register?'已有账号？登录':'还没有账号？注册';$('#auth-error').textContent='';$('#auth-form [name=password]').autocomplete=state.register?'new-password':'current-password';}
function confirmAction(title,message,button='继续'){
  return new Promise(resolve=>{const dialog=$('#confirm-dialog');$('#confirm-title').textContent=title;$('#confirm-message').textContent=message;$('#confirm-ok').textContent=button;let answer=false;$('#confirm-ok').onclick=()=>{answer=true;dialog.close();};$('#confirm-cancel').onclick=()=>dialog.close();dialog.onclose=()=>resolve(answer);dialog.showModal();});
}
function emptyEntries(){const logged=Boolean(state.user);$('#entries').innerHTML=`<div class="empty">${icon('book-open')}<h3>${logged?(hasFilters()?'还没有找到这一页':'今天，从第一篇开始'):'留一个角落，给自己'}</h3><button class="${logged?'text-button':'primary'}" id="empty-action">${logged?(hasFilters()?'查看全部日记':'写下今天'):'登录 / 注册'}</button></div>`;$('#empty-action').onclick=()=>!logged?openAuth():hasFilters()?resetFilters():openEditor();}
function hasFilters(){return state.date||$('#search').value||$('#period').value||$('#mood-filter').value||$('#tag-filter').value;}
function renderEntries(){
  if(!state.entries.length){emptyEntries();return;}
  $('#entries').innerHTML=state.entries.map(entry=>`<article class="entry-row" tabindex="0" role="button" data-id="${entry.id}" aria-label="打开日记：${esc(entry.title)}"><div class="entry-date"><time datetime="${entry.entry_date}">${dateLabel(entry.entry_date)}</time><small>${weekday(entry.entry_date)}</small><span class="mood-badge">${icon(moodIcons[entry.mood])}${esc(entry.mood)}</span></div><div class="entry-body" data-user-content><h3>${esc(entry.title)}</h3><p>${esc(entry.content)}</p>${entry.tags.length?`<div class="entry-tags">${entry.tags.map(t=>`<span class="tag"># ${esc(t)}</span>`).join('')}</div>`:''}</div></article>`).join('');
  document.querySelectorAll('.entry-row').forEach(row=>{row.onclick=()=>openEditor(Number(row.dataset.id));row.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();row.click();}};});
}
async function loadEntries(append=false){
  const serial=++requestSerial;
  if(!state.user){state.entries=[];renderEntries();$('#load-more').hidden=true;return;}
  const params=new URLSearchParams();
  if($('#search').value)params.set('q',$('#search').value);
  if($('#period').value){params.set('start',dayBefore(Number($('#period').value)-1));params.set('end',today());}
  if($('#mood-filter').value)params.set('mood',$('#mood-filter').value);
  if($('#tag-filter').value)params.set('tag',$('#tag-filter').value);
  if(state.date)params.set('date',state.date);
  params.set('offset',append?state.entries.length:0);
  try{const result=await api('/entries?'+params);if(serial!==requestSerial)return;state.entries=append?state.entries.concat(result.entries):result.entries;state.total=result.total;renderEntries();$('#load-more').hidden=state.entries.length>=result.total;}catch(error){toast(error.message);}
}
async function loadOverview(){
  state.overview=state.user?await api('/overview'):{days:[],tags:[],total:0};
  const old=$('#tag-filter').value;$('#tag-filter').innerHTML='<option value="">全部标签</option>'+state.overview.tags.map(t=>`<option value="${esc(t)}">${esc(t)}</option>`).join('');$('#tag-filter').value=state.overview.tags.includes(old)?old:'';$('#tag-filter-wrap').hidden=!state.overview.tags.length;
  renderCalendar();drawCharts();
}
async function refresh(){await loadOverview();await loadEntries();}
function resetFilters(){$('#filters').reset();state.date='';$('#date-selection').hidden=true;loadEntries();renderCalendar();}
function selectDate(value){state.date=state.date===value?'':value;$('#date-selection').hidden=!state.date;$('#date-selection span').textContent=state.date?dateLabel(value):'';loadEntries();renderCalendar();}
function renderCalendar(){
  $('#calendar-title').textContent=month.toLocaleDateString(AppI18N.locale,{year:'numeric',month:'long'});
  const start=(month.getDay()+6)%7,days=new Date(month.getFullYear(),month.getMonth()+1,0).getDate();
  const recorded=new Set(state.overview.days.map(d=>d.date));
  let html=(AppI18N.language==='en'?['M','T','W','T','F','S','S']:['一','二','三','四','五','六','日']).map(d=>`<span class="day-label">${d}</span>`).join('')+'<span></span>'.repeat(start);
  for(let i=1;i<=days;i++){const value=dateISO(new Date(month.getFullYear(),month.getMonth(),i));html+=`<button class="${value===today()?'today ':''}${recorded.has(value)?'recorded ':''}${state.date===value?'selected':''}" data-date="${value}" aria-label="${value}${recorded.has(value)?'，有日记':''}" aria-pressed="${state.date===value}">${i}</button>`;}
  $('#calendar').innerHTML=html;document.querySelectorAll('[data-date]').forEach(b=>b.onclick=()=>{switchView('diary');selectDate(b.dataset.date);});
}
function chart(canvas,range,weekly=false){
  if(canvas.closest('[hidden]'))return;
  const width=canvas.clientWidth;if(!width)return;
  const height=Number(canvas.dataset.height || canvas.getAttribute('height')),ratio=window.devicePixelRatio||1;canvas.dataset.height=height;
  canvas.width=width*ratio;canvas.height=height*ratio;canvas.style.height=height+'px';const ctx=canvas.getContext('2d');ctx.scale(ratio,ratio);ctx.clearRect(0,0,width,height);
  const dates=[];const start=new Date();start.setHours(12,0,0,0);if(weekly)start.setDate(start.getDate()-(start.getDay()+6)%7);else start.setDate(start.getDate()-range+1);
  for(let i=0;i<range;i++){let d=new Date(start);d.setDate(d.getDate()+i);dates.push(dateISO(d));}
  const values=new Map(state.overview.days.map(d=>[d.date,d.score]));
  const left=AppI18N.language==='en'?64:44,right=14,top=14,bottom=30,w=width-left-right,h=height-top-bottom;
  ctx.font='11px -apple-system, PingFang SC, sans-serif';ctx.textAlign='right';ctx.fillStyle='#a29180';
  ['低落','疲惫','平静','松弛','开心'].forEach((name,i)=>{const y=top+h-i*h/4;ctx.fillText(AppI18N.t(name),left-9,y+4);ctx.strokeStyle='#eee6da';ctx.setLineDash([2,4]);ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(width-right,y);ctx.stroke();});
  ctx.setLineDash([]);ctx.strokeStyle='#ceb77c';ctx.lineWidth=1.7;let previous=false;const summary=[];
  dates.forEach((day,i)=>{const x=left+i*w/(range-1),score=values.get(day);if(score===undefined){previous=false;return;}const y=top+h-(score-1)*h/4;ctx.beginPath();if(previous){ctx.moveTo(previous.x,previous.y);ctx.lineTo(x,y);ctx.stroke();}ctx.fillStyle='#e5d096';ctx.beginPath();ctx.arc(x,y,4,0,Math.PI*2);ctx.fill();ctx.strokeStyle='#fffaf0';ctx.lineWidth=1;ctx.stroke();ctx.strokeStyle='#ceb77c';ctx.lineWidth=1.7;previous={x,y};summary.push(`${day} ${score}`);});
  ctx.fillStyle='#9b8b79';ctx.textAlign='center';dates.forEach((day,i)=>{if(range>7 && i%5!==0 && i!==range-1)return;ctx.fillText(weekly?(AppI18N.language==='en'?['S','M','T','W','T','F','S']:['日','一','二','三','四','五','六'])[parseDate(day).getDay()]:day.slice(5),left+i*w/(range-1),height-7);});
  canvas.setAttribute('aria-label',summary.length?'自选心情趋势：'+summary.join('；'):'这一段时间暂无心情记录');
  if(canvas.id==='mini-chart')$('#mini-empty').hidden=summary.length>0;
  if(canvas.id==='large-chart')$('#trend-description').textContent=summary.length?'根据自己选择的心情绘制；同一天多篇取均值。':'这段时间还没有心情记录。';
}
function drawCharts(){chart($('#mini-chart'),7,true);chart($('#large-chart'),Number($('#trend-range').value));}
function switchView(view){if(!requireUser())return;RelaxationPlayer.stop();if(view!=='games')GameRoom.leave();else GameRoom.enter();if(view!=='ledger')closeLedgerReports();state.view=view;for(const id of ['diary','moods','profile','ledger','games'])$('#'+id+'-view').hidden=view!==id;$('.hero').hidden=!['diary','moods'].includes(view);if(view==='profile')populateProfile();if(view==='ledger')loadLedger();document.querySelectorAll('[data-view]').forEach(b=>{b.classList.toggle('active',b.dataset.view===view);b.setAttribute('aria-current',b.dataset.view===view?'page':'false');});drawCharts();}
function editorStatus(message,error=false){const status=$('#editor-status');status.textContent=message;status.hidden=!message;status.classList.toggle('error',error);if(error)status.scrollIntoView({block:'nearest'});}
function chooseMood(mood){state.mood=mood;$('#mood-picker').innerHTML=Object.entries(moodIcons).map(([name,ic])=>`<button type="button" data-mood="${name}" class="${mood===name?'selected':''}" aria-pressed="${mood===name}">${icon(ic)}${name}</button>`).join('');document.querySelectorAll('[data-mood]').forEach(b=>b.onclick=()=>{if(state.busy)return;chooseMood(b.dataset.mood);state.dirty=true;$('#save-state').textContent='未保存';editorStatus('');});}
async function openEditor(id=null){
  if(!requireUser())return;
  try{
    const data=id?await api('/entries/'+id):null;
    state.editing=id;state.dirty=false;editorStatus('');$('#entry-form').reset();$('#entry-date').value=data?data.entry.entry_date:today();$('#entry-title').value=data?data.entry.title:'';$('#entry-content').value=data?data.entry.content:'';$('#entry-tags').value=data?data.entry.tags.join('，'):'';chooseMood(data?data.entry.mood:'平静');$('#delete-entry').hidden=!id;$('#save-state').textContent=id?'已保存':'';$('#entry-result').innerHTML=data&&data.analysis?reviewHTML(data.analysis,data.analysis_id):'';$('#word-count').textContent=$('#entry-content').value.length+' 字';$('#editor-dialog').showModal();loadActivityImages($('#entry-result'));
  }catch(error){toast(error.message);}
}
async function closeEditor(){if(state.busy){toast('正在保存或复盘，请稍候');return;}if(state.dirty&&!await confirmAction('离开这一页？','尚未保存的内容会丢失。','放弃修改'))return;$('#editor-dialog').close();}
function entryPayload(){return {title:$('#entry-title').value,content:$('#entry-content').value,mood:state.mood,entry_date:$('#entry-date').value,tags:$('#entry-tags').value.split(/[,，]/).map(t=>t.trim()).filter(Boolean)};}
function setBusy(busy){state.busy=busy;['#save-entry','#analyze-entry','#delete-entry'].forEach(s=>$(s).disabled=busy);$('#entry-form').setAttribute('aria-busy',busy);$('#entry-form').querySelectorAll('input,textarea').forEach(el=>el.readOnly=busy);$('#mood-picker').querySelectorAll('button').forEach(el=>el.disabled=busy);}
async function saveEntry(){
  if(!$('#entry-form').reportValidity())return false;
  if(state.editing&&!state.dirty)return 'saved';
  editorStatus('正在保存…');
  const payload=entryPayload();const result=await api('/entries'+(state.editing?'/'+state.editing:''),{method:state.editing?'PUT':'POST',body:payload});
  state.editing=result.entry.id;state.dirty=false;$('#entry-title').value=result.entry.title;$('#delete-entry').hidden=false;$('#save-state').textContent='已保存';$('#entry-result').innerHTML='';editorStatus('日记已保存。可以继续复盘，或关闭这一页。');
  // 保存已经完成；列表刷新失败不能把保存当成失败或阻止复盘。
  try{await refresh();}catch(error){toast('日记已保存，列表暂未刷新，请稍后刷新页面。');}
  return 'saved';
}
const activityNames={yoga:'轻柔瑜伽',music:'听歌放松',meal:'好好吃饭',walk:'轻松散步',rest:'安静休息',read:'读几页书'};
function clockLabel(minutes){const days=Math.floor(minutes/1440);return `${days?'次日 ':''}${String(Math.floor(minutes/60)%24).padStart(2,'0')}:${String(minutes%60).padStart(2,'0')}`;}
function activityPlanHTML(plan){
  if(!Array.isArray(plan)||!plan.length)return '<div class="plan-legacy"><h4>给自己一段放松时间</h4><p>这份旧复盘还没有活动时间线，重新复盘即可生成。</p><button type="button" class="secondary regenerate-plan">生成活动时间线</button></div>';
  const now=new Date(),start=now.getHours()*60+now.getMinutes(),total=plan.reduce((sum,step)=>sum+step.duration_minutes,0);let elapsed=0;
  return `<section class="activity-plan" aria-label="建议活动时间线"><div class="plan-heading"><div><span class="plan-eyebrow">留一点时间给自己</span><h3>接下来，慢慢来</h3></div><div class="plan-heading-tools"><span class="plan-total">${plan.length} 件小事 · ${total} 分钟</span>${RelaxationPlayer.speaker()}</div></div>${RelaxationPlayer.controls(total)}<p class="plan-caption">根据这次复盘生成的建议安排，可按精力调整或跳过。配图为活动示意。</p><label class="plan-start">从几点开始 <input type="time" aria-label="活动起始时间" value="${clockLabel(start)}" required><span>修改后，后续安排自动顺延</span></label><ol class="plan-timeline">${plan.map((step,i)=>{const offset=elapsed;elapsed+=step.duration_minutes;const category=Object.hasOwn(activityNames,step.category)?step.category:'rest',asset=step.activity_id||category;return `<li class="plan-step" data-offset="${offset}" data-duration="${step.duration_minutes}"><div class="plan-clock"><time class="step-start">${clockLabel(start+offset)}</time><span class="step-end">至 ${clockLabel(start+elapsed)}</span></div><article class="activity-card"><div class="activity-visual" data-category="${esc(asset)}" data-fallback="${category}" data-label="${esc(step.title)}"><img src="/static/images/activities/${category}.svg" alt="${esc(activityNames[category])}示意图" loading="lazy"><span class="image-status" role="status">活动示意图</span></div><div class="activity-copy"><span class="activity-duration">第 ${i+1} 步 · ${step.duration_minutes} 分钟</span><h4 data-user-content>${esc(step.title)}</h4><p data-user-content>${esc(step.description)}</p>${i<plan.length-1?'<span class="activity-next">结束后，进入下一件小事 ↓</span>':'<span class="activity-next">到这里就好，留意此刻的感受。</span>'}</div></article></li>`;}).join('')}</ol><p class="plan-finish">预计 <strong>${clockLabel(start+total)}</strong> 结束 · 不必全部完成，舒服最重要。</p></section>`;
}
function updatePlanTime(input){
  if(!input.value)return;
  const [hours,minutes]=input.value.split(':').map(Number),start=hours*60+minutes,plan=input.closest('.activity-plan');let end=start;
  plan.querySelectorAll('.plan-step:not([hidden])').forEach(step=>{const from=start+Number(step.dataset.offset);end=from+Number(step.dataset.duration);step.querySelector('.step-start').textContent=clockLabel(from);step.querySelector('.step-end').textContent='至 '+clockLabel(end);});plan.querySelector('.plan-finish strong').textContent=clockLabel(end);
}
async function loadActivityImages(target,retry=false){
  const visuals=Array.from(target.querySelectorAll('.activity-visual'));
  if(!visuals.length)return;
  const categories=[...new Set(visuals.map(el=>el.dataset.category))],uid=state.user?.id;
  // Re-rendering a review cancels its previous polling loop without affecting generation.
  const token={};target.imageRequest=token;
  function current(){return target.imageRequest===token&&state.user?.id===uid&&visuals.every(el=>el.isConnected)&&(!target.closest('dialog')||target.closest('dialog').open);}
  function render(images){
    for(const visual of visuals){
      const item=images[visual.dataset.category];if(!item)continue;
      const status=visual.querySelector('.image-status');status.replaceChildren();
      if(item.status==='succeeded'){
        const img=visual.querySelector('img');
        img.onload=()=>{if(current())status.textContent='AI 生成配图';};
        img.onerror=()=>{img.onload=null;img.onerror=null;img.src='/static/images/activities/'+visual.dataset.fallback+'.svg';status.textContent='配图加载失败，暂用示意图';const button=document.createElement('button');button.type='button';button.className='text-button';button.textContent='重试配图';button.onclick=()=>loadActivityImages(target,true);status.append(button);};
        img.alt=visual.dataset.label+' AI 配图';if(img.getAttribute('src')!==item.url)img.src=item.url;
        if(img.complete&&img.naturalWidth)status.textContent='AI 生成配图';
      }else if(item.status==='failed'){
        status.textContent=item.error||'配图生成失败，暂用示意图';
        const button=document.createElement('button');button.type='button';button.className='text-button';button.textContent='重试配图';button.onclick=()=>loadActivityImages(target,true);status.append(button);
      }else status.textContent=item.status==='unconfigured'?'图片服务未配置 · 活动示意图':'配图生成中… · 暂用示意图';
    }
  }
  try{
    visuals.forEach(el=>el.querySelector('.image-status').textContent='正在准备配图…');
    let result=await api('/activity-images',{method:'POST',body:{categories,retry}});
    while(current()){
      render(result.images);
      if(!Object.values(result.images).some(item=>['queued','running'].includes(item.status)))break;
      await new Promise(resolve=>setTimeout(resolve,3000));if(!current())return;
      result=await api('/activity-images?categories='+encodeURIComponent(categories.join(',')));
    }
  }catch(error){if(current())visuals.forEach(el=>{const status=el.querySelector('.image-status');status.textContent='配图暂未完成，正文与时间线已保留。';const button=document.createElement('button');button.type='button';button.className='text-button';button.textContent='重试配图';button.onclick=()=>loadActivityImages(target,true);status.append(button);});}
}
function reviewHTML(result,analysisId){return `<section class="review-result" data-analysis-id="${Number(analysisId)||0}"><h3>温柔复盘</h3><div class="emotions">${result.emotions.map(e=>`<span>${esc(e)}</span>`).join('')}</div><p data-user-content>${esc(result.summary)}</p>${[['food','好好吃饭'],['vitamins','一点营养科普'],['movement','让身体松一松'],['inspiration','可以看看']].map(([key,title])=>`<div class="review-section"><h4>${title}</h4><p data-user-content>${esc(result[key])}</p></div>`).join('')}${activityPlanHTML(result.activity_plan)}<p class="disclaimer">${esc(result.disclaimer)}</p></section>`;}
async function analyze(body,target,button){
  if(!requireUser())return;
  const consent=await confirmAction('开始温柔复盘','将所选日记发送至 DeepSeek 生成生活参考；活动类型将用于生成配图，不向图片服务发送日记正文。图片会在文字完成后继续生成。','开始复盘');if(!consent)return;
  const old=button.innerHTML,uid=state.user.id;button.disabled=true;button.textContent='正在复盘…';if(body.entry_id)editorStatus('日记已保存，正在复盘…');
  try{const result=await api('/analyze',{method:'POST',body:{...body,consent:true}});if(state.user?.id!==uid)return;if(body.entry_id&&state.dirty){toast('内容有新修改，请保存后重新复盘');return;}RelaxationPlayer.stop();target.innerHTML=reviewHTML(result.analysis,result.analysis_id);loadActivityImages(target);if(body.entry_id)editorStatus('日记已保存，复盘已完成。');target.scrollIntoView({behavior:'smooth',block:'nearest'});}catch(error){if(body.entry_id)editorStatus('日记已保存；复盘未完成：'+error.message+'。可点击“保存并复盘”重试。',true);else toast(error.message);}finally{button.innerHTML=old;button.disabled=false;}
}
async function init(){
  // 图标仅来自本地图标库；页面内容始终进行 HTML 转义。
  document.querySelector('[data-feather="sparkles"]').setAttribute('data-feather','feather');window.feather.replace();
  $('#today').textContent=dateLabel(today())+'　'+weekday(today());
  $('#mood-filter').innerHTML+=Object.keys(moodIcons).map(m=>`<option value="${m}">${m}</option>`).join('');
  $('#review-start').value=dayBefore(6);$('#review-end').value=today();
  document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>switchView(b.dataset.view));
  document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>$('#'+b.dataset.close).close());
  $('#write').onclick=()=>openEditor();$('#editor-close').onclick=closeEditor;
  $('#editor-dialog').addEventListener('cancel',e=>{e.preventDefault();closeEditor();});
  $('#auth-switch').onclick=()=>{state.register=!state.register;updateAuth();};
  $('#profile-open').onclick=()=>switchView('profile');
  setupAccountFeatures();GameRoom.setup();
  $('#auth-form').onsubmit=async e=>{e.preventDefault();$('#auth-submit').disabled=true;try{const fields={...Object.fromEntries(new FormData(e.target)),language:AppI18N.language};if(state.register&&fields.password!==fields.confirm_password)throw new Error('确认密码不一致');const registering=state.register;const result=await api(registering?'/register':'/login',{method:'POST',body:fields});state.user=result.user;updateProfile();$('#auth-dialog').close();e.target.reset();await refresh();switchView(registering?'profile':'diary');}catch(error){$('#auth-error').textContent=error.message;}finally{$('#auth-submit').disabled=false;}};
  $('#filters').onsubmit=e=>e.preventDefault();$('#search').oninput=()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>loadEntries(),250);};
  ['#period','#mood-filter','#tag-filter'].forEach(s=>$(s).onchange=()=>loadEntries());
  $('#clear-date').onclick=()=>selectDate(state.date);$('#load-more').onclick=()=>loadEntries(true);
  $('#prev-month').onclick=()=>{month.setMonth(month.getMonth()-1);renderCalendar();};$('#next-month').onclick=()=>{month.setMonth(month.getMonth()+1);renderCalendar();};
  $('#trend-range').onchange=drawCharts;window.addEventListener('resize',drawCharts);
  $('#entry-form').oninput=()=>{state.dirty=true;editorStatus('');$('#save-state').textContent='未保存';$('#word-count').textContent=$('#entry-content').value.length+' 字';};
  $('#entry-form').onsubmit=async e=>{e.preventDefault();if(state.busy)return;setBusy(true);try{if(await saveEntry()){$('#editor-dialog').close();toast('日记已保存，这一页收好了');}}catch(error){editorStatus('保存未完成：'+error.message,true);}finally{setBusy(false);}};
  $('#delete-entry').onclick=async()=>{if(state.busy||!state.editing)return;if(!await confirmAction('删除这一页？','删除后无法恢复。','删除日记'))return;setBusy(true);try{await api('/entries/'+state.editing,{method:'DELETE'});state.dirty=false;$('#editor-dialog').close();await refresh();toast('已删除');}catch(error){toast(error.message);}finally{setBusy(false);}};
  $('#analyze-entry').onclick=async()=>{if(state.busy)return;if(!$('#entry-form').reportValidity())return;setBusy(true);try{if(!state.editing||state.dirty){if(!await saveEntry())return;}await analyze({entry_id:state.editing},$('#entry-result'),$('#analyze-entry'));}catch(error){editorStatus('保存未完成：'+error.message,true);}finally{setBusy(false);}};
  document.addEventListener('change',e=>{if(e.target.matches('.plan-start input'))updatePlanTime(e.target);});
  document.addEventListener('click',e=>{if(e.target.closest('.regenerate-plan')){if(e.target.closest('#entry-result'))$('#analyze-entry').click();else $('#period-review-form').requestSubmit();}});
  $('#period-review-form').onsubmit=async e=>{e.preventDefault();if($('#review-start').value>$('#review-end').value){toast('开始日期不能晚于结束日期');return;}await analyze({start:$('#review-start').value,end:$('#review-end').value},$('#period-result'),e.target.querySelector('button'));};
  window.addEventListener('beforeunload',e=>{if(state.dirty){e.preventDefault();e.returnValue='';}});
  try{const result=await api('/session');state.user=result.user;updateProfile();await refresh();}catch(error){updateProfile();toast(error.message);emptyEntries();renderCalendar();drawCharts();}
}
init();
