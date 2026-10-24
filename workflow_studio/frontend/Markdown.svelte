<script>
import {marked,Renderer} from 'marked';
import DOMPurify from 'dompurify';
import {copyText} from './bridge.js';
let {text='',class:className=''}=$props();
const renderer=new Renderer();
const renderCode=renderer.code.bind(renderer);
const renderTable=renderer.table.bind(renderer);
renderer.table=(...args)=>`<div class="markdown-table">${renderTable(...args)}</div>`;
renderer.code=(code,language,escaped)=>`<div class="code-block"><button type="button" class="code-copy" aria-label="复制代码" data-copy-code>复制代码</button>${renderCode(code,language,escaped)}</div>`;
let blocks=$derived(marked.lexer(text||'',{gfm:true,breaks:true}).map(token=>DOMPurify.sanitize(marked.parser([token],{gfm:true,breaks:true,renderer}))));
async function copyCode(event){
  const button=event.target.closest('[data-copy-code]');
  if(!button)return;
  try{await copyText(button.parentElement.querySelector('code').textContent);button.textContent='已复制';}
  catch{button.textContent='复制失败';}
}
function codeButtons(node){node.addEventListener('click',copyCode);return{destroy(){node.removeEventListener('click',copyCode);}};}
</script>
<div class={'markdown '+className} use:codeButtons>
  {#each blocks as block,index (index)}{@html block}{/each}
</div>
