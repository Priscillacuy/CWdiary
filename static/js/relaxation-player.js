/* Local protected media; nothing plays until the user presses Start. */
window.RelaxationPlayer=(()=>{
  'use strict';
  let active=null,pending=null,preparation=0;
  const t=value=>AppI18N.t(value);
  const languageNames={zh:'普通话（简体中文）','zh-HK':'粤语（中国香港）','zh-TW':'国语（中国台湾）',en:'English'};
  const selectedLanguage=plan=>plan.querySelector('.relax-language').value==='auto'?AppI18N.language:plan.querySelector('.relax-language').value;
  function languageHint(plan){plan.querySelector('.relax-language-current').textContent=t('当前朗读：')+t(languageNames[selectedLanguage(plan)]);}

  const label=seconds=>`${String(Math.floor(Math.ceil(seconds)/60)).padStart(2,'0')}:${String(Math.ceil(seconds)%60).padStart(2,'0')}`;
  function controls(total){
    const sleep=new Date().getHours()>=21||new Date().getHours()<6;
    return `<div class="relax-controls" hidden><p class="relax-intro">给自己一段有声音陪伴的时间。轻音乐会持续播放，每段结束会提醒下一步。</p><div class="relax-settings"><label>朗读语言<select class="relax-language" aria-label="朗读语言"><option value="auto">跟随界面语言</option>${Object.entries(languageNames).map(([id,name])=>`<option value="${id}">${name}</option>`).join('')}</select></label><label>陪伴声音<select class="relax-voice" aria-label="陪伴声音"><option value="female">温暖女声</option><option value="male">温暖男声</option></select></label><label>放松时长（分钟）<input class="relax-minutes" type="number" min="1" max="${total}" value="${total}" aria-label="放松时长（分钟）"></label><label>结束祝福<select class="relax-mode" aria-label="结束祝福"><option value="day" ${sleep?'':'selected'}>日间放松</option><option value="sleep" ${sleep?'selected':''}>睡前放松</option></select></label></div><p class="relax-language-current">${t('当前朗读：')}${t(languageNames[AppI18N.language])}</p><div class="relax-actions"><button type="button" class="primary relax-main">准备声音</button><button type="button" class="secondary relax-next" hidden>下一项</button><button type="button" class="text-button relax-stop" hidden>结束本次</button><label class="relax-volume">音乐音量<input class="relax-level" type="range" min="0" max="0.5" step="0.01" value="0.2" aria-label="音乐音量"></label></div><p class="relax-privacy">仅本次活动文案交给 DeepSeek 改写成口语，再由 ElevenLabs 配音，不发送日记原文。</p><div class="relax-now"><strong class="relax-status" role="status">选择声音与时长，准备好后再开始。</strong><span class="relax-countdown" aria-label="本项剩余时间">--:--</span></div><p class="relax-transcript" data-user-content></p><p class="relax-note">请保持此页面打开；设备休眠时，语音提醒可能延迟。</p></div>`;
  }
  function speaker(){return `<button type="button" class="relax-speaker" aria-label="打开声音与计时" aria-expanded="false" title="声音与计时">${icon('volume-2')}</button>`;}
  function status(plan,text){plan.querySelector('.relax-status').textContent=t(text);}
  function enableSettings(plan,enabled){plan.querySelectorAll('.relax-settings input,.relax-settings select:not(.relax-language)').forEach(el=>el.disabled=!enabled);plan.querySelector('.plan-start input').disabled=!enabled;}
  function setButton(plan,text){plan.querySelector('.relax-main').textContent=t(text);}
  function idleIcon(plan){const button=plan.querySelector('.relax-speaker');button.innerHTML=icon('volume-2');button.setAttribute('aria-label',t('打开声音与计时'));button.setAttribute('aria-pressed','false');}
  function sessionTimeline(a){
    const steps=Array.from(a.plan.querySelectorAll('.plan-step'));
    a.original={total:a.plan.querySelector('.plan-total').textContent,steps:steps.map(el=>({offset:el.dataset.offset,duration:el.dataset.duration,label:el.querySelector('.activity-duration').textContent,next:el.querySelector('.activity-next').textContent}))};
    let offset=0;
    steps.forEach((el,i)=>{el.hidden=i>=a.data.steps.length;if(el.hidden)return;const minutes=a.data.steps[i].duration_seconds/60;el.dataset.offset=offset;el.dataset.duration=minutes;el.querySelector('.activity-duration').textContent=t(`第 ${i+1} 步 · ${minutes} 分钟`);el.querySelector('.activity-next').textContent=t(i===a.data.steps.length-1?'到这里就好，留意此刻的感受。':'结束后，进入下一件小事 ↓');offset+=minutes;});
    a.plan.querySelector('.plan-total').textContent=t(`${a.data.steps.length} 件小事 · ${a.data.minutes} 分钟`);
  }
  function restoreTimeline(a){
    if(!a.original)return;
    a.plan.querySelector('.plan-total').textContent=a.original.total;
    a.plan.querySelectorAll('.plan-step').forEach((el,i)=>{const old=a.original.steps[i];el.hidden=false;el.dataset.offset=old.offset;el.dataset.duration=old.duration;el.querySelector('.activity-duration').textContent=old.label;el.querySelector('.activity-next').textContent=old.next;});
    updatePlanTime(a.plan.querySelector('.plan-start input'));
  }
  function remainingSchedule(a,view){
    const now=new Date();let minutes=now.getHours()*60+now.getMinutes();
    a.plan.querySelectorAll('.plan-step').forEach((el,i)=>{if(el.hidden||i<view.index)return;el.querySelector('.step-start').textContent=clockLabel(minutes);minutes+=Math.ceil((i===view.index?view.remaining:a.data.steps[i].duration_seconds)/60);el.querySelector('.step-end').textContent=t('至 '+clockLabel(minutes));});
    a.plan.querySelector('.plan-finish strong').textContent=clockLabel(minutes);
  }
  function stop(message='已结束本次放松，可以随时重新开始。'){
    preparation++;
    if(pending){pending.querySelector('.relax-main').disabled=false;enableSettings(pending,true);setButton(pending,'准备声音');status(pending,message);pending=null;}
    if(!active)return;
    const a=active;active=null;clearInterval(a.interval);a.clock?.stop();
    for(const audio of [a.music,a.narration])if(audio){audio.pause();audio.removeAttribute('src');audio.load();audio.remove();}
    a.plan.querySelectorAll('.plan-step').forEach(el=>el.classList.remove('is-current','is-complete'));
    restoreTimeline(a);
    enableSettings(a.plan,true);a.plan.querySelector('.relax-main').disabled=false;setButton(a.plan,a.data?'重新开始':'准备声音');idleIcon(a.plan);
    a.plan.querySelector('.relax-countdown').textContent='--:--';
    a.plan.querySelector('.relax-transcript').textContent='';
    a.plan.querySelector('.relax-next').hidden=true;a.plan.querySelector('.relax-stop').hidden=true;status(a.plan,message);
  }
  function volumes(a){a.music.volume=a.muted?0:(a.speaking?0.035:Number(a.plan.querySelector('.relax-level').value));a.narration.volume=a.muted?0:0.9;}
  function announce(a,item){
    if(active!==a)return;
    a.plan.querySelector('.relax-transcript').textContent=item.text;
    a.narration.pause();a.narration.src=item.voice_url;a.speaking=true;volumes(a);
    a.narration.play().catch(()=>{if(active===a){a.speaking=false;volumes(a);status(a.plan,'语音播放被阻止，请暂停后继续；文字引导与计时仍可使用。');}});
  }
  function update(a){
    if(active!==a)return;
    if(!a.plan.isConnected||a.plan.closest('[hidden]')||a.plan.closest('dialog')&&!a.plan.closest('dialog').open){stop();return;}
    const view=a.clock.snapshot();a.plan.querySelector('.relax-countdown').textContent=label(view.remaining);
    if(view.phase==='finished'){
      if(a.finished)return;
      a.finished=true;clearInterval(a.interval);a.music.pause();
      a.plan.querySelectorAll('.plan-step').forEach((el,i)=>{el.classList.remove('is-current');el.classList.toggle('is-complete',i<a.data.steps.length);});
      status(a.plan,'放松时间结束了，谢谢你照顾自己。');setButton(a.plan,'重新开始');
      a.plan.querySelector('.relax-next').hidden=true;enableSettings(a.plan,true);announce(a,a.data.closing);return;
    }
    if(view.index!==a.index){
      a.index=view.index;
      a.plan.querySelectorAll('.plan-step').forEach((el,i)=>{el.classList.toggle('is-current',i===view.index);el.classList.toggle('is-complete',i<view.index);});
      const prefix=AppI18N.language==='en'?`Step ${view.index+1} / ${a.data.steps.length}: `:`第 ${view.index+1} / ${a.data.steps.length} 项：`;
      status(a.plan,prefix+a.data.steps[view.index].title);announce(a,a.data.steps[view.index]);
    }
  }
  function start(a){
    if(active!==a)return;
    sessionTimeline(a);
    const now=new Date(),time=a.plan.querySelector('.plan-start input');time.value=`${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`;updatePlanTime(time);
    a.music=new Audio(a.data.music_url);a.music.loop=true;a.music.preload='auto';a.narration=new Audio();a.narration.preload='auto';a.muted=false;a.index=-1;a.finished=false;a.speaking=false;
    a.music.className='relax-music';a.narration.className='relax-narration';a.music.hidden=true;a.narration.hidden=true;a.plan.querySelector('.relax-controls').append(a.music,a.narration);
    a.narration.onended=()=>{if(active!==a)return;a.speaking=false;volumes(a);};
    a.narration.onerror=()=>{if(active!==a)return;a.speaking=false;volumes(a);status(a.plan,'语音暂不可用，文字引导与计时仍在继续。');};
    a.music.onerror=()=>{if(active===a)status(a.plan,'音乐暂不可用，语音引导与计时仍在继续。');};
    volumes(a);a.clock=new RelaxationClock(a.data.steps.map(step=>step.duration_seconds));a.clock.start();
    enableSettings(a.plan,false);setButton(a.plan,'暂停');a.plan.querySelector('.relax-next').hidden=false;a.plan.querySelector('.relax-next').disabled=false;a.plan.querySelector('.relax-stop').hidden=false;
    a.plan.querySelector('.relax-speaker').setAttribute('aria-label',t('静音'));a.plan.querySelector('.relax-speaker').setAttribute('aria-pressed','true');
    a.music.play().catch(()=>{if(active===a)status(a.plan,'音乐播放被阻止，请暂停后继续。');});update(a);a.interval=setInterval(()=>update(a),250);
  }
  async function loadAudio(plan,serial){
    const body={analysis_id:Number(plan.closest('.review-result').dataset.analysisId),minutes:Number(plan.querySelector('.relax-minutes').value),voice:plan.querySelector('.relax-voice').value,mode:plan.querySelector('.relax-mode').value,language:selectedLanguage(plan),consent:true};
    let data=await api('/relaxation/prepare',{method:'POST',body});
    while(data.status==='preparing'){
      await new Promise(resolve=>setTimeout(resolve,1500));
      if(serial!==preparation||!plan.isConnected||plan.closest('dialog')&&!plan.closest('dialog').open)return null;
      data=await api('/relaxation/sessions/'+data.session_id);
    }
    if(serial!==preparation)return null;
    if(data.status!=='ready')throw new Error(data.error||'声音准备未完成，请重试');
    if(data.language!==body.language)throw new Error('朗读语言不一致，请重新准备声音');
    return data;
  }
  async function prepare(plan){
    stop();const serial=++preparation;const main=plan.querySelector('.relax-main');
    const input=plan.querySelector('.relax-minutes');if(!input.reportValidity())return;
    pending=plan;main.disabled=true;enableSettings(plan,false);languageHint(plan);status(plan,'正在准备本次声音，请稍候…');
    try{
      const data=await loadAudio(plan,serial);if(!data)return;
      plan.relaxData=data;active={plan,data,clock:null};setButton(plan,'开始放松');status(plan,'声音已准备好，点击开始放松。');
    }catch(error){if(serial===preparation)status(plan,error.message);}
    finally{if(serial===preparation){pending=null;main.disabled=false;if(!active?.clock)enableSettings(plan,true);}}
  }
  async function languageChanged(plan){
    languageHint(plan);
    if(active?.plan!==plan||!active.clock){
      if(active?.plan===plan||pending===plan)stop();
      plan.relaxData=null;plan.querySelector('.relax-main').disabled=false;enableSettings(plan,true);setButton(plan,'准备声音');status(plan,'朗读语言已更改，请准备新语言声音。');return;
    }
    const a=active,serial=++preparation,main=plan.querySelector('.relax-main');
    if(a.switchRunning===undefined)a.switchRunning=a.clock.snapshot().phase==='running';
    pending=plan;a.clock.pause();a.music.pause();a.narration.pause();main.disabled=true;
    plan.querySelector('.relax-next').disabled=true;status(plan,'正在切换朗读语言，计时已暂停…');
    try{
      const data=await loadAudio(plan,serial);if(!data||active!==a)return;
      a.data=data;plan.relaxData=data;
      const view=a.clock.snapshot(),item=data.steps[view.index];a.index=-1;
      if(view.phase==='finished'){announce(a,data.closing);setButton(plan,'重新开始');status(plan,'放松时间结束了，谢谢你照顾自己。');}
      else if(a.switchRunning){a.clock.resume();a.music.play().catch(()=>{});setButton(plan,'暂停');plan.querySelector('.relax-next').disabled=false;update(a);}
      else{a.index=view.index;a.narration.src=item.voice_url;a.speaking=true;volumes(a);plan.querySelector('.relax-transcript').textContent=item.text;setButton(plan,'继续');status(plan,'已暂停，继续后将使用新语言朗读。');}
      delete a.switchRunning;
    }catch(error){if(serial===preparation){stop();plan.relaxData=null;setButton(plan,'准备声音');status(plan,error.message);}}
    finally{if(serial===preparation){pending=null;main.disabled=false;}}
  }
  function main(plan){
    if(active?.plan===plan&&active.clock){
      const a=active,view=a.clock.snapshot();
      if(view.phase==='running'){a.clock.pause();a.music.pause();a.narration.pause();plan.querySelector('.relax-next').disabled=true;setButton(plan,'继续');status(plan,'已暂停，准备好后继续。');}
      else if(view.phase==='paused'){const resumed=a.clock.resume();remainingSchedule(a,resumed);a.music.play().catch(()=>{});if(a.speaking)a.narration.play().catch(()=>{});plan.querySelector('.relax-next').disabled=false;setButton(plan,'暂停');status(plan,'放松正在继续，按照自己的节奏就好。');update(a);}
      else{stop();prepare(plan);}return;
    }
    if(active?.plan===plan&&active.data){start(active);return;}
    prepare(plan);
  }
  document.addEventListener('click',event=>{
    const plan=event.target.closest('.activity-plan');if(!plan)return;
    if(event.target.closest('.relax-speaker')){
      const panel=plan.querySelector('.relax-controls'),button=plan.querySelector('.relax-speaker');
      if(active?.plan===plan&&active.clock&&!active.finished){active.muted=!active.muted;volumes(active);button.innerHTML=icon(active.muted?'volume-x':'volume-2');button.setAttribute('aria-label',t(active.muted?'恢复声音':'静音'));button.setAttribute('aria-pressed',String(!active.muted));}
      else{panel.hidden=!panel.hidden;button.setAttribute('aria-expanded',String(!panel.hidden));}
    }
    if(event.target.closest('.relax-main'))main(plan);
    if(event.target.closest('.relax-stop'))stop();
    if(event.target.closest('.relax-next')&&active?.plan===plan&&active.clock){
      const previous=active.clock.snapshot(),view=active.clock.skip(),el=active.plan.querySelectorAll('.plan-step')[previous.index];
      if(el){const now=new Date();el.querySelector('.step-end').textContent=t('至 '+clockLabel(now.getHours()*60+now.getMinutes()));el.querySelector('.activity-duration').textContent=t('已提前结束');el.querySelector('.activity-next').textContent=t('按自己的节奏，继续下一项。');}
      remainingSchedule(active,view);update(active);
    }
  });
  document.addEventListener('input',event=>{if(event.target.matches('.relax-level')&&active?.music&&active.plan===event.target.closest('.activity-plan'))volumes(active);});
  document.addEventListener('change',event=>{if(event.target.matches('.relax-language')){languageChanged(event.target.closest('.activity-plan'));return;}if(event.target.matches('.relax-settings input,.relax-settings select')){const plan=event.target.closest('.activity-plan');if(active?.plan===plan)stop();plan.relaxData=null;setButton(plan,'准备声音');status(plan,'设置已更改，请重新准备声音。');}});
  document.addEventListener('app:languagechange',()=>{document.querySelectorAll('.activity-plan').forEach(plan=>{if(plan.querySelector('.relax-language')?.value==='auto')languageChanged(plan);});});
  document.addEventListener('visibilitychange',()=>{if(active?.clock)update(active);});
  document.addEventListener('close',event=>{if(event.target.id!=='editor-dialog')return;if(active?.plan&&event.target.contains(active.plan))stop();else preparation++;},true);
  window.addEventListener('pagehide',()=>stop());
  return {controls,speaker,stop};
})();
