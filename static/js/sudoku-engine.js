/* Offline beginner Sudoku: every generated puzzle is solvable by single candidates. */
(function(root){
  'use strict';
  const peers=(a,b)=>Math.floor(a/9)===Math.floor(b/9)||a%9===b%9||Math.floor(a/27)===Math.floor(b/27)&&Math.floor(a%9/3)===Math.floor(b%9/3);
  function candidates(board,index){if(board[index])return [];return [1,2,3,4,5,6,7,8,9].filter(n=>!board.some((v,i)=>v===n&&peers(i,index)));}
  function solved(board){return board.length===81&&board.every((n,i)=>Number.isInteger(n)&&n>=1&&n<=9&&!board.some((v,j)=>j!==i&&v===n&&peers(i,j)));}
  function singles(board){board=board.slice();let changed=true;while(changed){changed=false;for(let i=0;i<81;i++)if(!board[i]){const options=candidates(board,i);if(options.length===1){board[i]=options[0];changed=true;}}}return solved(board);}
  function shuffled(values,random){const out=values.slice();for(let i=out.length-1;i>0;i--){const j=Math.floor(random()*(i+1));[out[i],out[j]]=[out[j],out[i]];}return out;}
  function generate(random=Math.random){
    const order=()=>shuffled([0,1,2],random).flatMap(b=>shuffled([0,1,2],random).map(r=>b*3+r));
    const rows=order(),cols=order(),digits=shuffled([1,2,3,4,5,6,7,8,9],random);
    const solution=rows.flatMap(r=>cols.map(c=>digits[(r*3+Math.floor(r/3)+c)%9]));const puzzle=solution.slice();let removed=0;
    for(const i of shuffled(Array.from({length:81},(_,i)=>i),random)){const old=puzzle[i];puzzle[i]=0;if(singles(puzzle))removed++;else puzzle[i]=old;if(removed===36)break;}
    return {puzzle,solution};
  }
  function validSave(record){
    const values=a=>Array.isArray(a)&&a.length===81&&a.every(n=>Number.isInteger(n)&&n>=0&&n<=9);
    return Boolean(record&&record.version===1&&values(record.puzzle)&&values(record.solution)&&values(record.cells)&&solved(record.solution)&&record.puzzle.every((n,i)=>!n||n===record.solution[i]&&n===record.cells[i])&&Array.isArray(record.marks)&&record.marks.every(i=>Number.isInteger(i)&&i>=0&&i<81&&!record.puzzle[i])&&Number.isInteger(record.selected)&&record.selected>=-1&&record.selected<81);
  }
  const engine={generate,candidates,solved,singles,validSave};root.SudokuEngine=engine;if(typeof module!=='undefined')module.exports=engine;
})(typeof window!=='undefined'?window:globalThis);
