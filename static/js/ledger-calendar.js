'use strict';
// Both ledger fields keep ISO values for the existing form/API; only the view is localized.
const LedgerCalendar=(()=>{
  let popup,active,month;
  const buttons=()=>[...document.querySelectorAll('.warm-date-trigger')];
  const date=s=>{const [y,m,d]=s.split('-').map(Number);return new Date(y,m-1,d,12);};
  const iso=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  const format=(d,options)=>new Intl.DateTimeFormat(AppI18N.locale,options).format(d);
  const words=()=>AppI18N.language==='en'?{prev:'Previous month',next:'Next month',today:'Today',close:'Close',choose:'Choose a date'}:{prev:'上个月',next:'下个月',today:'今天',close:'关闭',choose:'选择日期'};
  function sync(){buttons().forEach(b=>{const value=document.getElementById(b.dataset.dateInput).value;if(!value)return;const d=date(value);b.innerHTML=`<span data-user-content>${format(d,{year:'numeric',month:'2-digit',day:'2-digit'})}<small>${format(d,{weekday:'long'})}</small></span>${feather.icons.calendar.toSvg({'aria-hidden':'true'})}`;});}
  function close(focus=false){if(!active)return;const b=active;popup.hidden=true;b.setAttribute('aria-expanded','false');active=null;if(focus)b.focus();}
  function choose(value){const input=document.getElementById(active.dataset.dateInput);input.value=value;sync();close(true);input.dispatchEvent(new Event('change',{bubbles:true}));}
  function render(focusDate){
    const w=words(),selected=document.getElementById(active.dataset.dateInput).value;
    const start=new Date(month.getFullYear(),month.getMonth(),1,12),offset=start.getDay();
    const headings=Array.from({length:7},(_,i)=>`<span data-user-content>${format(new Date(2026,10,1+i,12),{weekday:'narrow'})}</span>`).join('');
    const days=Array.from({length:42},(_,i)=>{const d=new Date(start);d.setDate(i-offset+1);const value=iso(d),outside=d.getMonth()!==month.getMonth();return `<button type="button" data-day="${value}" class="calendar-day${outside?' outside':''}${value===selected?' selected':''}${value===iso(new Date())?' today':''}" aria-label="${format(d,{year:'numeric',month:'long',day:'numeric',weekday:'long'})}" ${value===selected?'aria-current="date"':''} tabindex="${value===(focusDate||selected)?'0':'-1'}">${d.getDate()}</button>`;}).join('');
    popup.innerHTML=`<div class="warm-calendar-heading"><button type="button" data-month="-1" aria-label="${w.prev}">${feather.icons['chevron-left'].toSvg({'aria-hidden':'true'})}</button><strong data-user-content>${format(month,{year:'numeric',month:'long'})}</strong><button type="button" data-month="1" aria-label="${w.next}">${feather.icons['chevron-right'].toSvg({'aria-hidden':'true'})}</button></div><div class="warm-calendar-weekdays">${headings}</div><div class="warm-calendar-days">${days}</div><div class="warm-calendar-footer"><button type="button" data-today>${w.today}</button><button type="button" data-close>${w.close}</button></div>`;
    popup.setAttribute('aria-label',w.choose);
    popup.querySelectorAll('[data-day]').forEach(b=>b.onclick=()=>choose(b.dataset.day));
    popup.querySelectorAll('[data-month]').forEach(b=>b.onclick=()=>{month=new Date(month.getFullYear(),month.getMonth()+Number(b.dataset.month),1,12);render();popup.querySelector(`[data-month="${b.dataset.month}"]`).focus();});
    popup.querySelector('[data-today]').onclick=()=>choose(iso(new Date()));
    popup.querySelector('[data-close]').onclick=()=>close(true);
    // A displayed month always has one keyboard entry point, even without the selection.
    if(!popup.querySelector('.calendar-day[tabindex="0"]'))popup.querySelector('.calendar-day:not(.outside)').tabIndex=0;
    if(focusDate)popup.querySelector(`[data-day="${focusDate}"]`)?.focus();
  }
  function open(b){if(active===b){close();return;}close();active=b;month=date(document.getElementById(b.dataset.dateInput).value);render();popup.hidden=false;b.setAttribute('aria-expanded','true');const r=b.getBoundingClientRect(),width=Math.min(304,innerWidth-24);popup.style.width=width+'px';popup.style.left=Math.max(12,Math.min(r.left,innerWidth-width-12))+'px';const height=popup.offsetHeight;popup.style.top=Math.max(12,Math.min(r.bottom+8,innerHeight-height-12))+'px';popup.querySelector('.calendar-day[tabindex="0"]').focus({preventScroll:true});}
  function setup(){
    popup=document.createElement('div');popup.className='warm-calendar';popup.id='ledger-calendar';popup.role='dialog';popup.hidden=true;document.body.append(popup);
    buttons().forEach(b=>{b.setAttribute('aria-controls',popup.id);b.onclick=()=>open(b);});
    document.addEventListener('pointerdown',e=>{if(active&&!popup.contains(e.target)&&!active.contains(e.target))close();});
    document.addEventListener('focusin',e=>{if(active&&!popup.contains(e.target)&&e.target!==active)close();});
    document.addEventListener('keydown',e=>{if(!active)return;if(e.key==='Escape'){e.preventDefault();close(true);return;}const day=e.target.closest('[data-day]');if(!day)return;let d=date(day.dataset.day);const delta={ArrowLeft:-1,ArrowRight:1,ArrowUp:-7,ArrowDown:7}[e.key];if(delta)d.setDate(d.getDate()+delta);else if(e.key==='Home')d.setDate(d.getDate()-d.getDay());else if(e.key==='End')d.setDate(d.getDate()+6-d.getDay());else if(e.key==='PageUp'||e.key==='PageDown'){const n=d.getDate();d.setDate(1);d.setMonth(d.getMonth()+(e.key==='PageUp'?-1:1));d.setDate(Math.min(n,new Date(d.getFullYear(),d.getMonth()+1,0).getDate()));}else return;e.preventDefault();month=new Date(d.getFullYear(),d.getMonth(),1,12);render(iso(d));});
    document.addEventListener('app:languagechange',()=>{close();sync();});
    window.addEventListener('resize',()=>close());window.addEventListener('scroll',()=>close(),true);
  }
  return {setup,sync};
})();
