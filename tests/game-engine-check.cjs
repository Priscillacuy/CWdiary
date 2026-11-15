const assert=require('node:assert/strict');
const sudoku=require('../static/js/sudoku-engine.js');
const puzzle=require('../static/js/2048-engine.js');
for(let i=0;i<100;i++){
 const {puzzle:board,solution}=sudoku.generate();
 assert(sudoku.solved(solution));assert(!sudoku.solved(board));assert(sudoku.singles(board));
 assert(board.filter(v=>!v).length>=30);assert(board.every((v,i)=>!v||v===solution[i]));
}
assert.deepEqual([...puzzle.milestones(999)],[]);
assert.deepEqual([...puzzle.milestones(1000)],[1000]);
assert.deepEqual([...puzzle.milestones(2000,[1000])],[2000]);
assert.deepEqual([...puzzle.milestones(2048,[1000,2000])],[2048]);
assert.deepEqual([...puzzle.milestones(3000,[1000,2000,2048])],[3000]);
assert.deepEqual([...puzzle.milestones(1000,[1000,2000,2048])],[]); // Undo must not reward twice.
assert.deepEqual([...puzzle.milestones(1000)],[1000]); // New round resets claims.
console.log('100 Sudoku puzzles and 7 score celebration cases passed');

const sample=sudoku.generate();const saved={version:1,...sample,cells:sample.puzzle.slice(),marks:[],selected:sample.puzzle.indexOf(0)};
assert(sudoku.validSave(saved));
assert(!sudoku.validSave({...saved,cells:[]}));
assert(!sudoku.validSave({...saved,marks:[81]}));
const given=sample.puzzle.findIndex(Boolean),modified=saved.cells.slice();modified[given]=0;
assert(!sudoku.validSave({...saved,cells:modified}));
assert(!sudoku.validSave({...saved,solution:Array(81).fill(1)}));
console.log('Sudoku saved-progress validation passed');
const animated=puzzle.move([2,2,2,2,...Array(12).fill(0)],'left');
assert.deepEqual([...animated.merged],[0,1]);
assert.deepEqual(animated.transitions.map(t=>[t.from,t.to]),[[0,0],[1,0],[2,1],[3,1]]);
for(let i=0;i<100;i++){
 const board=Array.from({length:16},()=>Math.random()<.3?0:2**(1+Math.floor(Math.random()*7)));
 for(const direction of ['left','right','up','down']){
  const result=puzzle.move(board,direction),reconstructed=Array(16).fill(0);
  result.transitions.forEach(t=>{assert.equal(t.value,board[t.from]);reconstructed[t.to]+=t.value;});
  assert.deepEqual(reconstructed,[...result.board]);
  assert.equal(new Set(result.transitions.map(t=>t.from)).size,board.filter(Boolean).length);
 }
}
const record={version:1,numbers:[2,4,...Array(14).fill(0)],score:4,keepPlaying:false,roundId:'test-round',completed:false,milestones:[],undo:null};
assert(puzzle.validSave(record));assert(!puzzle.validSave({...record,numbers:Array(16).fill(3)}));assert(!puzzle.validSave({...record,score:-1}));assert(!puzzle.validSave({...record,undo:{numbers:[]}}));
console.log('400 tile-motion mappings and 2048 saved progress validated');
