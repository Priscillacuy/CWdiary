/* Offline games. Completion totals are saved per account in this browser. */
window.GameRoom=(()=>{
  'use strict';
  const $=s=>document.querySelector(s),t=s=>AppI18N.t(s),en=()=>AppI18N.language==='en';
  const svg=name=>window.feather.icons[name].toSvg({'aria-hidden':'true'});
  const faces=[['cat','猫咪'],['dog','小狗'],['rabbit','兔子'],['fox','狐狸'],['panda','熊猫'],['bear','小熊']];
  const avatars=faces.map(([animal])=>{const img=new Image();img.src='/static/images/avatars/watercolor-'+animal+'.webp';img.alt='';return img;});
  let account='',wins={},awarded=new Set(),celebration=null;
  let ready=false,selected='',deck=[],flipped=[],matched=new Set(),turns=0,mismatch=null;
  let sudoku=null,sudokuCells=[],sudokuSelected=-1,sudokuError=-1,sudokuMarks=new Set();
  let numbers=Array(16).fill(0),score=0,undo=null,keepPlaying=false,touch=null,scoreCelebrations=new Set();
  function setUser(id){
    const next=id==null?'':String(id);if(account===next)return;account=next;
    try{wins=JSON.parse(localStorage.getItem('cwdiary-game-wins:'+account)||'{}')||{};}catch{wins={};}
    if(ready){resetMemory();resetSudoku();resetPuzzle();renderWins();}
  }
  function renderWins(){
    for(const game of ['memory','sudoku','puzzle']){
      let card=$('#'+game+'-panel .game-wins');
      if(!card){card=document.createElement('aside');card.className='game-wins';card.setAttribute('aria-live','polite');$('#'+game+'-panel').append(card);}
      card.replaceChildren();const title=document.createElement('span');title.textContent=t('累计通关');const count=document.createElement('strong');count.textContent=String(Number.isSafeInteger(wins[game])&&wins[game]>0?wins[game]:0);const note=document.createElement('small');note.textContent=t('每一次进步，都值得庆祝');card.append(title,count,note);
    }
  }
  function celebrate(){
    if(celebration){clearInterval(celebration.interval);clearTimeout(celebration.timer);celebration.canvas.remove();}
    const canvas=document.createElement('canvas');canvas.className='game-confetti';canvas.setAttribute('aria-hidden','true');document.body.append(canvas);
    const burst=window.confetti.create(canvas,{resize:true,disableForReducedMotion:true});
    const fire=()=>{for(const x of [.12,.88])burst({particleCount:32,spread:75,startVelocity:38,gravity:.85,ticks:90,origin:{x,y:.65},colors:['#dba45f','#99af7d','#e7c465','#d58d78','#fff2cc']});};
    fire();const current={canvas,interval:setInterval(fire,450)};current.timer=setTimeout(()=>{clearInterval(current.interval);burst.reset();canvas.remove();if(celebration===current)celebration=null;},3600);celebration=current;
  }
  function complete(game){
    if(awarded.has(game))return;awarded.add(game);
    wins[game]=(Number.isSafeInteger(wins[game])&&wins[game]>0?wins[game]:0)+1;
    if(account)try{localStorage.setItem('cwdiary-game-wins:'+account,JSON.stringify(wins));}catch{}
    renderWins();celebrate();
  }
  function resetMemory(){awarded.delete('memory');clearTimeout(mismatch);mismatch=null;deck=[0,1,2,3,4,5,0,1,2,3,4,5];for(let i=deck.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[deck[i],deck[j]]=[deck[j],deck[i]];}flipped=[];matched=new Set();turns=0;renderMemory();}
  function renderMemory(){
    const board=$('#memory-board'),focused=Array.from(board.children).indexOf(document.activeElement);
    resetLabel('memory',matched.size===12?'won':'playing');
    $('#memory-status').textContent=matched.size===12?t('全部配对成功，做得很好！'):(en()?`Pairs ${matched.size/2} / 6 · Turns ${turns}`:`已配对 ${matched.size/2} / 6 · 翻牌 ${turns} 次`);
    $('#memory-board').replaceChildren(...deck.map((face,i)=>{const visible=matched.has(i)||flipped.includes(i),button=document.createElement('button');button.type='button';button.className='memory-tile'+(matched.has(i)?' is-matched':'');button.disabled=matched.has(i);button.setAttribute('aria-pressed',String(visible));button.setAttribute('aria-label',en()?`Card ${i+1}${visible?': '+t(faces[face][1]):''}`:`第 ${i+1} 张牌${visible?'：'+faces[face][1]:''}`);if(visible)button.append(avatars[face].cloneNode());else button.innerHTML=svg('help-circle');button.onclick=()=>flip(i);return button;}));
    if(focused>=0)(!board.children[focused].disabled?board.children[focused]:board.querySelector('button:enabled'))?.focus({preventScroll:true});
  }
  function clearMismatch(){clearTimeout(mismatch);mismatch=null;flipped=[];if(deck.length)renderMemory();}
  function flip(i){if(mismatch||matched.has(i)||flipped.includes(i))return;flipped.push(i);if(flipped.length===2){turns++;if(deck[flipped[0]]===deck[flipped[1]]){flipped.forEach(n=>matched.add(n));flipped=[];if(matched.size===12)complete('memory');}else mismatch=setTimeout(clearMismatch,800);}renderMemory();}
  function resetLabel(game,result){$('#'+game+'-reset').textContent=t(result==='won'?'开启新一局':result==='lost'?'再来一局':'重新开始');}
  function resetSudoku(){
    awarded.delete('sudoku');sudokuMarks.clear();sudoku=SudokuEngine.generate();sudokuCells=sudoku.puzzle.slice();sudokuSelected=sudokuCells.indexOf(0);sudokuError=-1;renderSudoku();
  }
  function renderSudoku(message){
    const won=SudokuEngine.solved(sudokuCells);resetLabel('sudoku',won?'won':'playing');
    $('#sudoku-status').textContent=t(message||(won?'数独完成了，做得很好！':'选择一个空格，再点下方数字；卡住时可以用提示。'));
    $('#sudoku-board').replaceChildren(...sudokuCells.map((value,i)=>{
      const button=document.createElement('button');button.type='button';button.className='sudoku-cell'+(sudoku.puzzle[i]?' is-given':'')+(i===sudokuSelected?' is-selected':'')+(i===sudokuError?' is-error':'')+(sudokuMarks.has(i)?' is-marked':'');button.textContent=value||'';button.disabled=Boolean(sudoku.puzzle[i])||won;button.setAttribute('aria-label',en()?`Row ${Math.floor(i/9)+1}, column ${i%9+1}: ${value||'empty'}`:`第 ${Math.floor(i/9)+1} 行第 ${i%9+1} 列：${value||'空格'}`);if(sudokuMarks.has(i))button.setAttribute('aria-description',t('已标注为不确定'));button.setAttribute('aria-pressed',String(i===sudokuSelected));button.onclick=()=>{sudokuSelected=i;sudokuError=-1;renderSudoku();};return button;
    }));
    $('#sudoku-mark').disabled=won||sudokuSelected<0||Boolean(sudoku.puzzle[sudokuSelected]);$('#sudoku-mark').setAttribute('aria-pressed',String(sudokuMarks.has(sudokuSelected)));
    $('#sudoku-panel').querySelectorAll('[data-sudoku-number],#sudoku-hint').forEach(b=>b.disabled=won);
  }
  function fillSudoku(value,hint=false){
    if(SudokuEngine.solved(sudokuCells))return;
    if(hint&&(sudokuSelected<0||sudoku.puzzle[sudokuSelected]||sudokuCells[sudokuSelected]===sudoku.solution[sudokuSelected]))sudokuSelected=sudokuCells.findIndex((n,i)=>!sudoku.puzzle[i]&&n!==sudoku.solution[i]);
    if(sudokuSelected<0||sudoku.puzzle[sudokuSelected])return;
    const i=sudokuSelected;value=hint?sudoku.solution[i]:value;sudokuCells[i]=value;if(!value||hint)sudokuMarks.delete(i);sudokuError=value&&value!==sudoku.solution[i]?i:-1;
    if(SudokuEngine.solved(sudokuCells))complete('sudoku');
    renderSudoku(sudokuError>=0?'不要气馁，换个数字试试，也可以点提示。':undefined);
  }
  function addNumber(){const empty=numbers.map((value,index)=>value?-1:index).filter(i=>i>=0);if(empty.length)numbers[empty[Math.floor(Math.random()*empty.length)]]=Math.random()<0.9?2:4;}
  function puzzleBlocked(){return numbers.some(value=>value>=2048)&&!keepPlaying||!Puzzle2048.canMove(numbers);}
  function renderPuzzle(){
    $('#puzzle-score').textContent=String(score);$('#puzzle-undo').disabled=!undo;
    const won=numbers.some(value=>value>=2048)&&!keepPlaying,stuck=!Puzzle2048.canMove(numbers);
    $('#puzzle-continue').hidden=!won;resetLabel('puzzle',won?'won':stuck?'lost':'playing');
    $('#puzzle-status').textContent=t(won?'合成 2048 了！可以继续挑战更大的数字。':stuck?'继续努力！不要气馁，试试撤销或新的一局。':'把相同的数字合在一起，向 2048 出发。');
    $('#puzzle-board').replaceChildren(...numbers.map((value,index)=>{const cell=document.createElement('div');cell.className='puzzle-cell';cell.dataset.value=value;cell.textContent=value?String(value):'';cell.setAttribute('aria-label',en()?`Cell ${index+1}: ${value||'empty'}`:`第 ${index+1} 格：${value||'空格'}`);return cell;}));
    document.querySelectorAll('[data-direction]').forEach(button=>button.disabled=puzzleBlocked());
  }
  function resetPuzzle(){awarded.delete('puzzle');scoreCelebrations.clear();numbers=Array(16).fill(0);score=0;undo=null;keepPlaying=false;addNumber();addNumber();renderPuzzle();}
  function movePuzzle(direction){
    if(puzzleBlocked())return;const result=Puzzle2048.move(numbers,direction);if(!result.changed)return;
    undo={numbers:numbers.slice(),score,keepPlaying};numbers=result.board;score+=result.score;addNumber();
    let milestone=false;for(const mark of Puzzle2048.milestones(score,[...scoreCelebrations])){scoreCelebrations.add(mark);milestone=true;}
    const newWin=numbers.some(value=>value>=2048)&&!awarded.has('puzzle');
    if(newWin)complete('puzzle');else if(milestone)celebrate();renderPuzzle();
  }
  function leave(){if(!ready)return;if(mismatch)clearMismatch();touch=null;}
  function choose(name){leave();selected=name;renderWins();for(const id of ['memory','sudoku','puzzle'])$('#'+id+'-panel').hidden=id!==name;document.querySelectorAll('[data-game]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.game===name)));if(name==='memory')renderMemory();if(name==='sudoku')renderSudoku();if(name==='puzzle')renderPuzzle();}
  function enter(){if(selected)choose(selected);}
  function setup(){
    if(ready)return;ready=true;
    document.querySelectorAll('[data-game]').forEach(button=>button.onclick=()=>choose(button.dataset.game));$('#memory-reset').onclick=resetMemory;$('#sudoku-reset').onclick=resetSudoku;$('#puzzle-reset').onclick=resetPuzzle;
    $('#puzzle-undo').onclick=()=>{if(!undo)return;numbers=undo.numbers;score=undo.score;keepPlaying=undo.keepPlaying;undo=null;renderPuzzle();};
    $('#puzzle-continue').onclick=()=>{keepPlaying=true;renderPuzzle();};
    document.querySelectorAll('[data-direction]').forEach(button=>button.onclick=()=>movePuzzle(button.dataset.direction));
    document.addEventListener('keydown',event=>{if(selected!=='puzzle'||$('#games-view').hidden||event.target.closest('input,select,textarea,[contenteditable=true]')||event.ctrlKey||event.metaKey||event.altKey)return;const keys={ArrowLeft:'left',ArrowRight:'right',ArrowUp:'up',ArrowDown:'down',a:'left',d:'right',w:'up',s:'down'};if(keys[event.key]){event.preventDefault();movePuzzle(keys[event.key]);}});
    document.querySelectorAll('[data-sudoku-number]').forEach(b=>b.onclick=()=>fillSudoku(Number(b.dataset.sudokuNumber)));$('#sudoku-hint').onclick=()=>fillSudoku(0,true);$('#sudoku-mark').onclick=()=>{if(SudokuEngine.solved(sudokuCells)||sudokuSelected<0||sudoku.puzzle[sudokuSelected])return;if(sudokuMarks.has(sudokuSelected))sudokuMarks.delete(sudokuSelected);else sudokuMarks.add(sudokuSelected);renderSudoku();};
    document.addEventListener('keydown',event=>{if(selected!=='sudoku'||$('#games-view').hidden||event.target.closest('input,select,textarea,[contenteditable=true]')||event.ctrlKey||event.metaKey||event.altKey)return;if(/^[1-9]$/.test(event.key)){event.preventDefault();fillSudoku(Number(event.key));}else if(['Backspace','Delete','0'].includes(event.key)){event.preventDefault();fillSudoku(0);}});
    const board=$('#puzzle-board');board.addEventListener('pointerdown',event=>{if(!event.isPrimary||event.button!==0)return;touch={x:event.clientX,y:event.clientY,id:event.pointerId};board.setPointerCapture(event.pointerId);});
    board.addEventListener('pointerup',event=>{if(!touch||touch.id!==event.pointerId)return;const dx=event.clientX-touch.x,dy=event.clientY-touch.y;touch=null;if(Math.max(Math.abs(dx),Math.abs(dy))<24)return;movePuzzle(Math.abs(dx)>Math.abs(dy)?dx>0?'right':'left':dy>0?'down':'up');});
    board.addEventListener('pointercancel',()=>touch=null);
    resetMemory();resetSudoku();resetPuzzle();document.addEventListener('visibilitychange',()=>{if(document.hidden)leave();});window.addEventListener('pagehide',leave);
  }
  return {setup,leave,enter,setUser};
})();
