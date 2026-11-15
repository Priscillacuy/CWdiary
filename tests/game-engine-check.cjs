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
