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
    const next=board.slice();let score=0;
    for(let track=0;track<4;track++){
      let indices=Array.from({length:4},(_,offset)=>direction==='left'||direction==='right'?track*4+offset:offset*4+track);
      if(direction==='right'||direction==='down')indices.reverse();
      const result=slideLine(indices.map(i=>board[i]));score+=result.score;indices.forEach((index,j)=>next[index]=result.line[j]);
    }
    return {board:next,score,changed:next.some((value,i)=>value!==board[i])};
  }
  function canMove(board){return board.some(value=>!value)||['left','up'].some(direction=>move(board,direction).changed);}
  function milestones(score,claimed=[]){return [...Array.from({length:Math.floor(score/1000)},(_,i)=>(i+1)*1000),2048].filter(n=>n<=score&&!claimed.includes(n)).sort((a,b)=>a-b);}
  const engine={slideLine,move,canMove,milestones};root.Puzzle2048=engine;if(typeof module!=='undefined')module.exports=engine;
})(typeof window!=='undefined'?window:globalThis);
