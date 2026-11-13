/* Local games only: no fetch, server calls, tracking or persistent user data. */
window.GameRoom=(()=>{
  'use strict';
  const $=s=>document.querySelector(s),t=s=>AppI18N.t(s),en=()=>AppI18N.language==='en';
  const svg=name=>window.feather.icons[name].toSvg({'aria-hidden':'true'});
  const faces=[['cat','猫咪'],['dog','小狗'],['rabbit','兔子'],['fox','狐狸'],['panda','熊猫'],['bear','小熊']];
  const avatars=faces.map(([animal])=>{const img=new Image();img.src='/static/images/avatars/watercolor-'+animal+'.webp';img.alt='';return img;});
  let ready=false,selected='',deck=[],flipped=[],matched=new Set(),turns=0,mismatch=null;
  let cells=Array(9).fill(''),over=false;
  let numbers=Array(16).fill(0),score=0,undo=null,keepPlaying=false,touch=null;
  const lines=[[0,1,2],[3,4,5],[6,7,8],[0,3,6],[1,4,7],[2,5,8],[0,4,8],[2,4,6]];
  function resetMemory(){clearTimeout(mismatch);mismatch=null;deck=[0,1,2,3,4,5,0,1,2,3,4,5];for(let i=deck.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[deck[i],deck[j]]=[deck[j],deck[i]];}flipped=[];matched=new Set();turns=0;renderMemory();}
  function renderMemory(){
    const board=$('#memory-board'),focused=Array.from(board.children).indexOf(document.activeElement);
    $('#memory-status').textContent=matched.size===12?t('全部配对成功，做得很好！'):(en()?`Pairs ${matched.size/2} / 6 · Turns ${turns}`:`已配对 ${matched.size/2} / 6 · 翻牌 ${turns} 次`);
    $('#memory-board').replaceChildren(...deck.map((face,i)=>{const visible=matched.has(i)||flipped.includes(i),button=document.createElement('button');button.type='button';button.className='memory-tile'+(matched.has(i)?' is-matched':'');button.disabled=matched.has(i);button.setAttribute('aria-pressed',String(visible));button.setAttribute('aria-label',en()?`Card ${i+1}${visible?': '+t(faces[face][1]):''}`:`第 ${i+1} 张牌${visible?'：'+faces[face][1]:''}`);if(visible)button.append(avatars[face].cloneNode());else button.innerHTML=svg('help-circle');button.onclick=()=>flip(i);return button;}));
    if(focused>=0)(!board.children[focused].disabled?board.children[focused]:board.querySelector('button:enabled'))?.focus({preventScroll:true});
  }
  function clearMismatch(){clearTimeout(mismatch);mismatch=null;flipped=[];if(deck.length)renderMemory();}
  function flip(i){if(mismatch||matched.has(i)||flipped.includes(i))return;flipped.push(i);if(flipped.length===2){turns++;if(deck[flipped[0]]===deck[flipped[1]]){flipped.forEach(n=>matched.add(n));flipped=[];}else mismatch=setTimeout(clearMismatch,800);}renderMemory();}
  function winner(board){for(const line of lines)if(board[line[0]]&&line.every(i=>board[i]===board[line[0]]))return board[line[0]];return board.every(Boolean)?'draw':null;}
  function renderTic(){
    const board=$('#tictac-board'),focused=Array.from(board.children).indexOf(document.activeElement);
    const result=winner(cells);over=Boolean(result);
    $('#tictac-status').textContent=t(result==='X'?'你赢了，恭喜！':result==='O'?'电脑赢了，再来一局吧。':result==='draw'?'这一局平局，配合得刚刚好。':'轮到你了，选一个空格画叉。');
    $('#tictac-board').replaceChildren(...cells.map((value,i)=>{const button=document.createElement('button');button.type='button';button.className='tictac-cell';button.disabled=over||Boolean(value);button.setAttribute('aria-label',en()?`Row ${Math.floor(i/3)+1}, column ${i%3+1}: ${value||'empty'}`:`第 ${Math.floor(i/3)+1} 行第 ${i%3+1} 列：${value||'空格'}`);button.innerHTML=value?svg(value==='X'?'x':'circle'):'';button.onclick=()=>play(i);return button;}));
    if(focused>=0)board.querySelector('button:enabled')?.focus({preventScroll:true});
  }
  function play(i){
    if(over||cells[i])return;cells[i]='X';
    if(!winner(cells)){
      const empty=cells.map((v,n)=>v?-1:n).filter(n=>n>=0);
      let choice=-1;
      for(const mark of ['O','X']){choice=empty.find(n=>{const trial=cells.slice();trial[n]=mark;return winner(trial)===mark;})??-1;if(choice>=0)break;}
      if(choice<0)choice=empty.includes(4)?4:empty[Math.floor(Math.random()*empty.length)];
      cells[choice]='O';
    }
    renderTic();
  }
  function resetTic(){cells=Array(9).fill('');over=false;renderTic();}
  function addNumber(){const empty=numbers.map((value,index)=>value?-1:index).filter(i=>i>=0);if(empty.length)numbers[empty[Math.floor(Math.random()*empty.length)]]=Math.random()<0.9?2:4;}
  function puzzleBlocked(){return numbers.some(value=>value>=2048)&&!keepPlaying||!Puzzle2048.canMove(numbers);}
  function renderPuzzle(){
    $('#puzzle-score').textContent=String(score);$('#puzzle-undo').disabled=!undo;
    const won=numbers.some(value=>value>=2048)&&!keepPlaying,stuck=!Puzzle2048.canMove(numbers);
    $('#puzzle-continue').hidden=!won;
    $('#puzzle-status').textContent=t(won?'合成 2048 了！可以继续挑战更大的数字。':stuck?'没有可移动的空位了，试试撤销或新的一局。':'把相同的数字合在一起，向 2048 出发。');
    $('#puzzle-board').replaceChildren(...numbers.map((value,index)=>{const cell=document.createElement('div');cell.className='puzzle-cell';cell.dataset.value=value;cell.textContent=value?String(value):'';cell.setAttribute('aria-label',en()?`Cell ${index+1}: ${value||'empty'}`:`第 ${index+1} 格：${value||'空格'}`);return cell;}));
    document.querySelectorAll('[data-direction]').forEach(button=>button.disabled=puzzleBlocked());
  }
  function resetPuzzle(){numbers=Array(16).fill(0);score=0;undo=null;keepPlaying=false;addNumber();addNumber();renderPuzzle();}
  function movePuzzle(direction){if(puzzleBlocked())return;const result=Puzzle2048.move(numbers,direction);if(!result.changed)return;undo={numbers:numbers.slice(),score,keepPlaying};numbers=result.board;score+=result.score;addNumber();renderPuzzle();}
  function leave(){if(!ready)return;if(mismatch)clearMismatch();touch=null;}
  function choose(name){leave();selected=name;for(const id of ['memory','tictac','puzzle'])$('#'+id+'-panel').hidden=id!==name;document.querySelectorAll('[data-game]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.game===name)));if(name==='memory')renderMemory();if(name==='tictac')renderTic();if(name==='puzzle')renderPuzzle();}
  function enter(){if(selected)choose(selected);}
  function setup(){
    if(ready)return;ready=true;
    document.querySelectorAll('[data-game]').forEach(button=>button.onclick=()=>choose(button.dataset.game));$('#memory-reset').onclick=resetMemory;$('#tictac-reset').onclick=resetTic;$('#puzzle-reset').onclick=resetPuzzle;
    $('#puzzle-undo').onclick=()=>{if(!undo)return;numbers=undo.numbers;score=undo.score;keepPlaying=undo.keepPlaying;undo=null;renderPuzzle();};
    $('#puzzle-continue').onclick=()=>{keepPlaying=true;renderPuzzle();};
    document.querySelectorAll('[data-direction]').forEach(button=>button.onclick=()=>movePuzzle(button.dataset.direction));
    document.addEventListener('keydown',event=>{if(selected!=='puzzle'||$('#games-view').hidden||event.target.closest('input,select,textarea,[contenteditable=true]')||event.ctrlKey||event.metaKey||event.altKey)return;const keys={ArrowLeft:'left',ArrowRight:'right',ArrowUp:'up',ArrowDown:'down',a:'left',d:'right',w:'up',s:'down'};if(keys[event.key]){event.preventDefault();movePuzzle(keys[event.key]);}});
    const board=$('#puzzle-board');board.addEventListener('pointerdown',event=>{if(!event.isPrimary||event.button!==0)return;touch={x:event.clientX,y:event.clientY,id:event.pointerId};board.setPointerCapture(event.pointerId);});
    board.addEventListener('pointerup',event=>{if(!touch||touch.id!==event.pointerId)return;const dx=event.clientX-touch.x,dy=event.clientY-touch.y;touch=null;if(Math.max(Math.abs(dx),Math.abs(dy))<24)return;movePuzzle(Math.abs(dx)>Math.abs(dy)?dx>0?'right':'left':dy>0?'down':'up');});
    board.addEventListener('pointercancel',()=>touch=null);
    resetMemory();resetTic();resetPuzzle();document.addEventListener('visibilitychange',()=>{if(document.hidden)leave();});window.addEventListener('pagehide',leave);
  }
  return {setup,leave,enter};
})();
