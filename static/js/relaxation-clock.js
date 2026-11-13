/* Absolute elapsed time: interval throttling never extends the selected session. */
(function(root){
  'use strict';
  class RelaxationClock {
    constructor(durations, now=()=>Date.now()) {
      if(!durations.length||durations.some(n=>!Number.isFinite(n)||n<=0))throw new Error('Invalid durations');
      this.durations=durations;this.now=now;this.total=durations.reduce((a,b)=>a+b,0);this.elapsed=0;this.phase='idle';this.since=0;
    }
    start(){if(this.phase==='idle'){this.phase='running';this.since=this.now();}return this.snapshot();}
    snapshot(){
      const elapsed=Math.min(this.total,this.elapsed+(this.phase==='running'?Math.max(0,this.now()-this.since)/1000:0));
      if(elapsed>=this.total){this.phase='finished';this.elapsed=this.total;}
      let offset=0,index=0;
      while(index<this.durations.length&&elapsed>=offset+this.durations[index]){offset+=this.durations[index];index++;}
      return {phase:this.phase,index,elapsed,remaining:index<this.durations.length?Math.max(0,offset+this.durations[index]-elapsed):0,totalRemaining:Math.max(0,this.total-elapsed)};
    }
    pause(){const state=this.snapshot();if(this.phase==='running'){this.elapsed=state.elapsed;this.phase='paused';}return this.snapshot();}
    resume(){if(this.phase==='paused'){this.since=this.now();this.phase='running';}return this.snapshot();}
    skip(){const state=this.snapshot();if(!['running','paused'].includes(state.phase))return state;this.elapsed=this.durations.slice(0,state.index+1).reduce((a,b)=>a+b,0);this.since=this.now();return this.snapshot();}
    stop(){this.phase='idle';this.elapsed=0;return this.snapshot();}
  }
  root.RelaxationClock=RelaxationClock;
  if(typeof module!=='undefined')module.exports=RelaxationClock;
})(typeof window!=='undefined'?window:globalThis);
