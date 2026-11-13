'use strict';
const animals={cat:'猫咪',dog:'小狗',rabbit:'兔子',fox:'狐狸',panda:'熊猫',bear:'小熊'};
let ledgerItems=[],editingLedger=null,ledgerSaving=false,ledgerRequest=0,reportRequest=0;
const ledgerCurrencyNames={CNY:'人民币 RMB',HKD:'港币 HKD',TWD:'新台币 NTD',GBP:'英镑 GBP',USD:'美元 USD'};
const ledgerCurrency=()=>state.user?.currency||'CNY';
function setLanguage(language){
  AppI18N.set(language);$('#auth-language').value=AppI18N.language;
  $('#today').textContent=dateLabel(today())+'　'+weekday(today());
  renderEntries();renderCalendar();drawCharts();
  if(state.user)syncLedgerCurrency();
}
function populateProfile(){
  if(!state.user)return;
  $('#profile-username').value=state.user.username;$('#profile-nickname').value=state.user.nickname;
  $('#profile-gender').value=state.user.gender;$('#profile-language').value=state.user.language;
  $('#profile-currency').value=ledgerCurrency();syncLedgerCurrency();
  $('#avatar-preview').src=state.user.avatar_url;$('#profile-display-name').textContent=state.user.nickname;
  $('#animal-avatars').innerHTML=Object.entries(animals).map(([id,name])=>`<button type="button" data-avatar="${id}" aria-label="${name}" aria-pressed="${state.user.avatar===id}"><img src="/static/images/avatars/watercolor-${id}.webp" alt=""><span class="avatar-check" aria-hidden="true">${icon('check')}</span><span class="animal-name">${name}</span></button>`).join('');
  $('#animal-avatars').querySelectorAll('button').forEach(button=>button.onclick=async()=>{
    if(button.disabled)return;button.disabled=true;
    try{const result=await api('/profile',{method:'PATCH',body:{avatar:button.dataset.avatar}});state.user=result.user;updateProfile(false);$('#avatar-preview').src=state.user.avatar_url;$('#profile-display-name').textContent=state.user.nickname;$('#animal-avatars').querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',b.dataset.avatar===state.user.avatar));$('#avatar-status').textContent='头像已更新';}catch(error){$('#avatar-status').textContent=error.message;}finally{button.disabled=false;}
  });
}
function money(cents,currency=ledgerCurrency()){return new Intl.NumberFormat(AppI18N.locale,{style:'currency',currency,minimumFractionDigits:2,maximumFractionDigits:2}).format(cents/100);}
function syncLedgerCurrency(){const code=ledgerCurrency(),alias={CNY:'RMB',TWD:'NTD'}[code]||code;$('#ledger-currency-name').textContent=AppI18N.t(ledgerCurrencyNames[code]);$('#ledger-amount-label').textContent=AppI18N.t('金额')+'（'+alias+'）';}
function closeLedgerReports(){reportRequest++;$('#ledger-reports').open=false;$('#ledger-report-content').replaceChildren();}
async function loadLedgerReports(){
  const details=$('#ledger-reports'),target=$('#ledger-report-content');if(!details.open||!state.user)return;
  const requestId=++reportRequest,query=new URLSearchParams({date:$('#ledger-date').value,currency:ledgerCurrency()});
  target.innerHTML='<p class="muted small">正在读取收支…</p>';
  try{const result=await api('/ledger/summary?'+query);if(requestId!==reportRequest||!details.open)return;
    target.innerHTML='<div class="ledger-report-grid">'+['year','month'].map(kind=>{const report=result[kind],d=parseDate(report.period+(kind==='month'?'-01':'-01-01')),period=new Intl.DateTimeFormat(AppI18N.locale,kind==='month'?{year:'numeric',month:'long'}:{year:'numeric'}).format(d);return `<section class="ledger-report-card"><h3 data-user-content>${esc(period)}</h3><dl><div><dt>收入</dt><dd data-user-content>${money(report.income_cents,result.currency)}</dd></div><div><dt>支出</dt><dd data-user-content>${money(report.expense_cents,result.currency)}</dd></div><div class="report-balance"><dt>结余</dt><dd data-user-content>${money(report.balance_cents,result.currency)}</dd></div></dl></section>`;}).join('')+'</div>';
  }catch(error){if(requestId===reportRequest&&details.open)target.textContent=error.message;}
}
function syncLedgerCategory(){const value=$('#ledger-form [name=category]').value.trim();document.querySelectorAll('[data-ledger-category]').forEach(button=>button.setAttribute('aria-pressed',String(value===button.dataset.ledgerCategory||value===AppI18N.t(button.dataset.ledgerCategory))));}
function resetLedgerForm(){editingLedger=null;$('#ledger-form').reset();$('#ledger-form [name=entry_date]').value=$('#ledger-date').value||today();$('#ledger-form-title').textContent='记一笔';$('#ledger-cancel').hidden=true;syncLedgerCategory();LedgerCalendar.sync();}
async function loadLedger(){
  if(!state.user)return;
  syncLedgerCurrency();const requestId=++ledgerRequest,query=new URLSearchParams({date:$('#ledger-date').value,currency:ledgerCurrency()});
  if($('#ledger-reports').open)loadLedgerReports();
  try{const result=await api('/ledger?'+query);if(requestId!==ledgerRequest)return;ledgerItems=result.items;
    $('#ledger-expense').textContent=money(result.expense_cents);
    $('#ledger-items').innerHTML=result.items.length?result.items.map(item=>`<article class="ledger-row"><div><span class="ledger-kind">${item.kind==='income'?'收入':'支出'}</span><h3 data-user-content>${esc(item.category)}</h3><p class="muted small"><time>${item.entry_date}</time> <span data-user-content>${esc(item.note)}</span></p></div><strong class="ledger-amount ${item.kind}" data-user-content>${item.kind==='income'?'+':'−'}${money(item.amount_cents,item.currency)}</strong><div class="ledger-row-actions"><button type="button" class="text-button" data-edit-ledger="${item.id}">编辑</button><button type="button" class="text-button danger" data-delete-ledger="${item.id}">删除</button></div></article>`).join(''):'<p class="ledger-empty muted">这一天还没有收支记录</p>';
    $('#ledger-items').querySelectorAll('[data-edit-ledger]').forEach(button=>button.onclick=()=>{const item=ledgerItems.find(r=>r.id===Number(button.dataset.editLedger));editingLedger=item.id;for(const key of ['kind','category','note','entry_date'])$('#ledger-form [name='+key+']').value=item[key];$('#ledger-form [name=amount]').value=(item.amount_cents/100).toFixed(2);syncLedgerCategory();LedgerCalendar.sync();$('#ledger-form-title').textContent='编辑账目';$('#ledger-cancel').hidden=false;$('#ledger-form').scrollIntoView({block:'nearest'});});
    $('#ledger-items').querySelectorAll('[data-delete-ledger]').forEach(button=>button.onclick=async()=>{if(!await confirmAction('删除这笔账目？','删除后无法恢复。','删除'))return;try{await api('/ledger/'+button.dataset.deleteLedger,{method:'DELETE'});if(editingLedger===Number(button.dataset.deleteLedger))resetLedgerForm();await loadLedger();}catch(error){$('#ledger-status').textContent=error.message;}});
  }catch(error){if(requestId===ledgerRequest)$('#ledger-status').textContent=error.message;}
}
function setupAccountFeatures(){
  $('#auth-language').value=AppI18N.language;
  $('#auth-language').onchange=e=>setLanguage(e.target.value);
  $('#profile-language').onchange=e=>setLanguage(e.target.value);
  $('#profile-currency').onchange=()=>{$('#currency-status').textContent='';};
  $('#ledger-preferences-form').onsubmit=async e=>{e.preventDefault();const button=e.target.querySelector('button[type=submit]');button.disabled=true;try{const result=await api('/profile',{method:'PATCH',body:{currency:$('#profile-currency').value}});state.user=result.user;closeLedgerReports();syncLedgerCurrency();resetLedgerForm();await loadLedger();$('#currency-status').textContent='交易货币已保存';}catch(error){$('#currency-status').textContent=error.message;}finally{button.disabled=false;}};
  $('#ledger-reports').addEventListener('toggle',()=>{if($('#ledger-reports').open)loadLedgerReports();else{reportRequest++;$('#ledger-report-content').replaceChildren();}});
  $('#auth-dialog').addEventListener('cancel',e=>{if(!state.user)e.preventDefault();});
  $('#profile-form').onsubmit=async e=>{e.preventDefault();const button=e.target.querySelector('button[type=submit]');button.disabled=true;try{const result=await api('/profile',{method:'PATCH',body:{nickname:$('#profile-nickname').value,gender:$('#profile-gender').value,language:$('#profile-language').value}});state.user=result.user;$('#period-result').innerHTML='';$('#entry-result').innerHTML='';updateProfile();$('#profile-status').textContent='资料已保存';}catch(error){$('#profile-status').textContent=error.message;}finally{button.disabled=false;}};
  $('#avatar-upload').onchange=async e=>{const file=e.target.files[0];if(!file)return;const status=$('#avatar-status');if(file.size>2*1024*1024||!['image/png','image/jpeg','image/webp'].includes(file.type)){status.textContent='请上传2MB以内的PNG、JPG或WebP图片';e.target.value='';return;}status.textContent='正在上传头像…';e.target.disabled=true;try{const image=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=reject;reader.readAsDataURL(file);});const result=await api('/avatar',{method:'POST',body:{image}});state.user=result.user;updateProfile(false);$('#avatar-preview').src=state.user.avatar_url;$('#profile-display-name').textContent=state.user.nickname;$('#animal-avatars').querySelectorAll('button').forEach(button=>button.setAttribute('aria-pressed','false'));status.textContent='头像已更新';}catch(error){status.textContent=error.message;}finally{e.target.value='';e.target.disabled=false;}};
  $('#password-form').onsubmit=async e=>{e.preventDefault();const fields=Object.fromEntries(new FormData(e.target)),status=$('#password-status');if(fields.new_password!==fields.confirm_password){status.textContent='两次输入的新密码不一致';return;}const button=e.target.querySelector('button');button.disabled=true;try{await api('/password',{method:'POST',body:fields});e.target.reset();status.textContent='密码已更新，其他会话已退出';}catch(error){status.textContent=error.message;}finally{button.disabled=false;}};
  $('#logout').onclick=async()=>{try{await api('/logout',{method:'POST'});ledgerRequest++;closeLedgerReports();state.user=null;state.entries=[];state.dirty=false;$('#password-form').reset();$('#profile-form').reset();$('#ledger-preferences-form').reset();$('#currency-status').textContent='';$('#entry-form').reset();$('#entry-result').innerHTML='';$('#ledger-items').innerHTML='';resetLedgerForm();updateProfile();resetFilters();await refresh();}catch(error){toast(error.message);}};
  LedgerCalendar.setup();$('#ledger-date').value=today();$('#ledger-date').onchange=()=>{resetLedgerForm();loadLedger();};resetLedgerForm();
  $('#ledger-cancel').onclick=resetLedgerForm;
  document.querySelectorAll('[data-ledger-category]').forEach(button=>button.onclick=()=>{$('#ledger-form [name=category]').value=AppI18N.t(button.dataset.ledgerCategory);syncLedgerCategory();});
  $('#ledger-form [name=category]').addEventListener('input',syncLedgerCategory);
  $('#ledger-form').onsubmit=async e=>{e.preventDefault();if(ledgerSaving)return;ledgerSaving=true;const button=e.target.querySelector('button[type=submit]');button.disabled=true;try{const body={...Object.fromEntries(new FormData(e.target)),currency:ledgerCurrency()};await api('/ledger'+(editingLedger?'/'+editingLedger:''),{method:editingLedger?'PUT':'POST',body});$('#ledger-date').value=body.entry_date;resetLedgerForm();$('#ledger-status').textContent='账目已保存';await loadLedger();}catch(error){$('#ledger-status').textContent=error.message;}finally{button.disabled=false;ledgerSaving=false;}};
}
