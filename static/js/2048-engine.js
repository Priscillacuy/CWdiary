/* Pure local 2048 rules; randomness is deliberately outside the move operation. */
(function(root){
  'use strict';
  function slideLine(line){
    const values=line.filter(Boolean),out=[];let score=0;
    for(let i=0;i<values.length;i++){if(values[i]===values[i+1]){const merged=values[i]*2;out.push(merged);score+=merged;i++;}else out.push(values[i]);}
    while(out.length<4)out.push(0);return {line:out,score};
  }
  function move(board,direction){
    if(!['left','right','up','down'].includes(direction))throw new Error('Invalid direction');
    const next=board.slice();let score=0;const transitions=[],merged=[];
    for(let track=0;track<4;track++){
      let indices=Array.from({length:4},(_,offset)=>direction==='left'||direction==='right'?track*4+offset:offset*4+track);
      if(direction==='right'||direction==='down')indices.reverse();
      const occupied=indices.filter(i=>board[i]);let target=0;
      for(let i=0;i<occupied.length;i++){
        const from=occupied[i],to=indices[target++];transitions.push({from,to,value:board[from]});
        if(board[from]===board[occupied[i+1]]){transitions.push({from:occupied[++i],to,value:board[from]});merged.push(to);}
      }
      const result=slideLine(indices.map(i=>board[i]));score+=result.score;indices.forEach((index,j)=>next[index]=result.line[j]);
    }
    return {board:next,score,transitions,merged,changed:next.some((value,i)=>value!==board[i])};
  }
  function canMove(board){return board.some(value=>!value)||['left','up'].some(direction=>move(board,direction).changed);}
  function milestones(score,claimed=[]){return [...Array.from({length:Math.floor(score/1000)},(_,i)=>(i+1)*1000),2048].filter(n=>n<=score&&!claimed.includes(n)).sort((a,b)=>a-b);}
  function validSave(record){
    const board=b=>Array.isArray(b)&&b.length===16&&b.every(n=>n===0||Number.isInteger(n)&&n>=2&&n<=1073741824&&Math.log2(n)%1===0);
    const state=s=>s&&board(s.numbers)&&Number.isSafeInteger(s.score)&&s.score>=0&&typeof s.keepPlaying==='boolean';
    return Boolean(record&&record.version===1&&state(record)&&typeof record.roundId==='string'&&record.roundId.length>0&&record.roundId.length<100&&typeof record.completed==='boolean'&&Array.isArray(record.milestones)&&record.milestones.every(n=>Number.isSafeInteger(n)&&n>0&&(n%1000===0||n===2048))&&(!record.undo||state(record.undo)));
  }
  const engine={slideLine,move,canMove,milestones,validSave};root.Puzzle2048=engine;if(typeof module!=='undefined')module.exports=engine;
})(typeof window!=='undefined'?window:globalThis);
