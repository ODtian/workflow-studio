<script>
import {onMount} from 'svelte';
import {Button} from '$lib/components/ui/button';import {Badge} from '$lib/components/ui/badge';import {Input} from '$lib/components/ui/input';import {Textarea} from '$lib/components/ui/textarea';import {Switch} from '$lib/components/ui/switch';
import {Plus,ArrowUp,Square,Paperclip,Settings2,Wrench,Sparkles,History,GitBranch,Copy,Download,RefreshCw,X,MessageSquare,ChevronDown,Check,Terminal,FileText} from '@lucide/svelte';
import Field from './Field.svelte';import Markdown from './Markdown.svelte';import {readFile,copyText} from './bridge.js';import {followTail} from './followTail.js';
let {panel,active=true,values=$bindable(),pi={messages:[]},send,targets=[],onTransfer}=$props();
let input=$state(''),drawer=$state(''),attachments=$state([]),name=$state(''),skillName=$state(''),skillSource=$state(''),copied=$state(''),queue=$state([]),following=$state(true);
let skillEditorOpen=$state(false),skillSaving=$state(false),skillNotice=$state(''),skillSaveError=$state(false);
let scrollRequest=$state(0);
let imageInput,scrollPane;
let messages=$derived(pi.messages||[]);
let lastText=$derived(messages.filter(m=>m.role==='assistant').at(-1)?.content?.filter(p=>p.type==='text').map(p=>p.text).join('\n')||'');
const act=(action,data={})=>send('pi',{id:panel.id,params:{...values},command:{action,...data}});
const plain=content=>typeof content==='string'?content:(content||[]).filter(p=>p.type==='text').map(p=>p.text).join('\n');
let stats=$derived(pi.stats||{});
let context=$derived(stats.contextUsage);
let skillVersion='';
$effect(()=>{if(pi.editingSkill && pi.editingSkill.source!==skillVersion){skillVersion=pi.editingSkill.source;skillSource=pi.editingSkill.source;skillName=pi.editingSkill.path.split('/').at(-2);skillEditorOpen=true;skillNotice='';}});
$effect(()=>{const result=pi.skillSave;if(result){skillSaving=false;skillSaveError=Boolean(result.error);skillNotice=result.error||'已保存';}});
onMount(()=>act('inspect'));
function submit(action='prompt'){
  if(!input.trim()&&!attachments.length)return;
  act(action,{text:input,images:attachments});
  if(action==='steer'||action==='follow_up')queue=[...queue,{action,text:input}];else queue=[];
  input='';attachments=[];scrollRequest++;
}
function entryFor(message){return (pi.entries||[]).find(e=>e.role===message.role&&e.timestamp===message.timestamp);}
async function copy(text,key){try{await copyText(text);copied=key;}catch{copied='error:'+key;}}
function saveSkill(){skillSaving=true;skillNotice='';act('save_skill',{name:skillName,source:skillSource});}
</script>
<article class="pi-workspace" aria-label="Pi 对话">
  <div class="pi-heading"><div class="pi-avatar">π</div><div class="pi-heading-text"><h1>{pi.name||'Pi 对话'}</h1><p>本地模型 · 工具 · Skills</p></div>
    <div class="row"><Button variant="outline" size="sm" disabled={panel.busy} onclick={()=>{act('new');queue=[];}}><Plus size={14}/>新对话</Button>
    <Button variant={drawer==='sessions'?'secondary':'ghost'} size="icon" aria-label="会话历史" onclick={()=>drawer=drawer==='sessions'?'':'sessions'}><History size={17}/></Button>
    <Button variant={drawer==='skills'?'secondary':'ghost'} size="icon" aria-label="Skills 与资源" onclick={()=>drawer=drawer==='skills'?'':'skills'}><Sparkles size={17}/></Button>
    <Button variant={drawer==='tools'?'secondary':'ghost'} size="icon" aria-label="工具管理" onclick={()=>drawer=drawer==='tools'?'':'tools'}><Wrench size={17}/></Button>
    <Button variant={drawer==='settings'?'secondary':'ghost'} size="icon" aria-label="对话设置" onclick={()=>drawer=drawer==='settings'?'':'settings'}><Settings2 size={17}/></Button></div>
  </div>
  <div class="pi-body">
    <div class="conversation-column">
      <div class="conversation-scroll" bind:this={scrollPane} use:followTail={{key:pi.id,active,reset:scrollRequest,onChange:value=>following=value}}>
        <div class="conversation-thread">
        {#if !messages.length}<div class="chat-welcome"><div class="welcome-symbol">π</div><h2>从一个想法开始</h2><p>对话、读写文件、运行工具，或使用你的 skills。</p><div class="welcome-actions"><Button variant="outline" onclick={()=>{input='请使用 ls 工具查看当前工作目录。';}}>浏览工作目录</Button><Button variant="outline" onclick={()=>drawer='skills'}>查看 Skills</Button></div></div>{/if}
        {#each messages as message,index (`${message.timestamp}:${index}`)}
          {#if message.role==='user'}<div class="message user-message"><div class="message-label">你</div><div class="user-bubble"><Markdown text={plain(message.content)}/>{#if Array.isArray(message.content)}<div class="chat-images">{#each message.content.filter(p=>p.type==='image') as image}<img src={`data:${image.mimeType};base64,${image.data}`} alt="对话附件"/>{/each}</div>{/if}</div>
            <div class="message-actions"><Button variant="ghost" size="xs" onclick={()=>copy(plain(message.content),'user:'+index)}><Copy size={12}/>{copied==='user:'+index?'已复制':copied==='error:user:'+index?'复制失败':'复制'}</Button><Button variant="ghost" size="xs" disabled={panel.busy||!entryFor(message)} onclick={()=>{act('navigate',{entry:entryFor(message).id});input=plain(message.content);}}>编辑并分支</Button></div></div>
          {:else if message.role==='assistant'}<div class="message assistant-message"><div class="message-label"><span class="mini-pi">π</span> Pi</div>
            {#each message.content||[] as part}
              {#if part.type==='thinking'}<details class="thinking"><summary>思考过程 <ChevronDown size={13}/></summary><Markdown text={part.thinking}/><div class="message-actions"><Button variant="ghost" size="xs" onclick={()=>copy(part.thinking,'thinking:'+index)}><Copy size={12}/>{copied==='thinking:'+index?'已复制':copied==='error:thinking:'+index?'复制失败':'复制思考过程'}</Button></div></details>
              {:else if part.type==='text'}<Markdown text={part.text} class="assistant-text"/>
              {:else if part.type==='toolCall'}
                {@const result=messages.find(m=>m.role==='toolResult'&&m.toolCallId===part.id)}
                <details class="tool-call"><summary><Terminal size={14}/><strong>{part.name}</strong><span class="tool-summary">{Object.values(part.arguments||{})[0]?.toString().slice(0,85)}</span><Badge variant={result?.isError?'destructive':'secondary'}>{result?(result.isError?'出错':'完成'):'执行中'}</Badge><ChevronDown size={13}/></summary><div class="tool-body"><div class="tool-section-heading"><small>参数</small><Button variant="ghost" size="xs" onclick={()=>copy(JSON.stringify(part.arguments,null,2),'args:'+part.id)}><Copy size={12}/>{copied==='args:'+part.id?'已复制':'复制参数'}</Button></div><pre>{JSON.stringify(part.arguments,null,2)}</pre>{#if result}<div class="tool-section-heading"><small>执行结果</small><Button variant="ghost" size="xs" onclick={()=>copy(plain(result.content),'result:'+part.id)}><Copy size={12}/>{copied==='result:'+part.id?'已复制':'复制结果'}</Button></div><pre>{plain(result.content)}</pre>{/if}</div></details>
              {/if}
            {/each}
            {#if message.errorMessage}<p class="error-text">{message.errorMessage}</p>{/if}
            {#if plain(message.content)}<div class="message-actions"><Button variant="ghost" size="xs" onclick={()=>copy(plain(message.content),String(index))}>{#if copied===String(index)}<Check size={12}/>{:else}<Copy size={12}/>{/if}{copied===String(index)?'已复制':copied==='error:'+index?'复制失败':'复制'}</Button>{#if entryFor(message)}<Button variant="ghost" size="xs" disabled={panel.busy} onclick={()=>act('navigate',{entry:entryFor(message).id})}><GitBranch size={12}/>从这里分支</Button>{/if}</div>{/if}</div>
          {/if}
        {/each}
        {#if panel.busy}<div class="agent-running"><i class="status-dot pulse"></i>{panel.message}</div>{/if}
        </div>
      </div>
      <div class="composer-area">
        {#if !following}<Button variant="secondary" size="sm" class="follow-button" onclick={()=>scrollRequest++}>回到最新 <ChevronDown size={14}/></Button>{/if}
        {#if queue.length}<div class="queue-note">{#each queue as item}<span>{item.action==='steer'?'引导':'排队'} · {item.text}</span>{/each}</div>{/if}
        <div class="composer">
          {#if attachments.length}<div class="attachment-strip">{#each attachments as image,index}<div><img src={image.url} alt={image.name}/><button aria-label="移除附件" onclick={()=>attachments=attachments.filter((_,i)=>i!==index)}>×</button></div>{/each}</div>{/if}
          {#if input.startsWith('/')}<div class="slash-menu">{#each (pi.skills||[]).filter(s=>('/skill:'+s.name).includes(input.split(' ')[0])) as skill}<button onclick={()=>input='/skill:'+skill.name+' '}><Sparkles size={13}/>/skill:{skill.name}<small>{skill.description}</small></button>{/each}{#each pi.prompts||[] as prompt}<button onclick={()=>input='/'+prompt.name+' '}><FileText size={13}/>/{prompt.name}</button>{/each}</div>{/if}
          <Textarea aria-label="消息输入" placeholder="发送消息，输入 / 使用 skill 或提示模板…" rows={3} bind:value={input} onkeydown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();submit(panel.busy?'follow_up':'prompt');}}}/>
          <div class="composer-toolbar"><div class="row"><Button variant="ghost" size="icon-sm" aria-label="添加图片" onclick={()=>imageInput.click()}><Paperclip size={17}/></Button><button class="model-caption" onclick={()=>drawer='settings'}>{(values.model||'').split('/').at(-1)?.replace('.gguf','')}<ChevronDown size={12}/></button></div>
            <div class="row">{#if panel.busy}<Button variant="ghost" size="sm" disabled={!input.trim()} onclick={()=>submit('steer')}>引导</Button><Button variant="outline" size="sm" disabled={!input.trim()} onclick={()=>submit('follow_up')}>排队</Button><Button variant="destructive" size="icon" aria-label="停止生成" onclick={()=>send('cancel',{id:panel.id})}><Square size={13}/></Button>{:else}<Button size="icon" aria-label="发送消息" disabled={!input.trim()&&!attachments.length} onclick={()=>submit()}><ArrowUp size={18}/></Button>{/if}</div>
          </div>
        </div>
        <div class="composer-footer"><span>{pi.activeTools?.length||0} 个工具 · {pi.skills?.length||0} 个 skills</span><span>{context?.percent?`${context.percent.toFixed(0)}% 上下文 · `:''}{panel.metadata?.每秒tokens?panel.metadata.每秒tokens+' tok/s · ':''}Enter 发送 · Shift Enter 换行</span></div>
        {#if panel.phase==='error'}<p class="error-text">{panel.message}</p>{/if}
      </div>
    </div>
    {#if drawer}<aside class="pi-drawer"><div class="drawer-heading"><h2>{{settings:'对话设置',tools:'工具',skills:'Skills 与资源',sessions:'会话与分支'}[drawer]}</h2><Button variant="ghost" size="icon-sm" aria-label="关闭设置" onclick={()=>drawer=''}><X size={16}/></Button></div><div class="drawer-content">
      {#if drawer==='settings'}<p class="hint">{panel.initializing?panel.initialization:'模型参数随工作流保存。'}</p>{#each [...new Set(panel.spec.fields.map(f=>f.area||f.section||'参数'))] as group}<details class="settings-group" open={group==='models'||group==='生成'}><summary>{{models:'模型',prompts:'系统提示词',advanced:'高级设置'}[group]||group}</summary><div class="settings-fields">{#each panel.spec.fields.filter(f=>(f.area||f.section||'参数')===group) as field}<Field {field} bind:value={values[field.key]} busy={panel.busy}/>{/each}</div></details>{/each}<p class="hint path-text">{panel.spec.model_root}</p>
      {:else if drawer==='tools'}<p class="hint">工具调整将在下一轮推理生效。</p>{#each pi.tools||[] as tool}<div class="resource-row"><div><strong>{tool.name}</strong><p>{tool.description}</p></div><Switch aria-label={'启用 '+tool.name} checked={pi.activeTools?.includes(tool.name)} onCheckedChange={checked=>act('tools',{tools:checked?[...(pi.activeTools||[]),tool.name]:(pi.activeTools||[]).filter(t=>t!==tool.name)})}/></div>{/each}
      {:else if drawer==='skills'}<div class="row"><Button variant="outline" size="sm" disabled={panel.busy} onclick={()=>act('reload')}><RefreshCw size={13}/>重载资源</Button><Button variant="ghost" size="sm" onclick={()=>{skillName='';skillSource='---\nname: my-skill\ndescription: 描述这个 skill 的用途\n---\n\n在这里填写执行步骤。';skillEditorOpen=true;skillNotice='';}}>新建 Skill</Button></div><p class="hint">从项目 .pi/skills、.pi/prompts 与 .pi/extensions 加载。</p>
        {#each pi.skills||[] as skill}<div class="skill-card"><div class="row"><Sparkles size={15}/><strong>{skill.name}</strong></div><p>{skill.description}</p><div class="row"><Button variant="outline" size="sm" onclick={()=>{input='/skill:'+skill.name+' ';}}>使用</Button><Button variant="ghost" size="sm" onclick={()=>act('read_skill',{path:skill.filePath})}>编辑</Button></div></div>{/each}
        {#if !(pi.skills||[]).length}<div class="empty-resource">添加 SKILL.md 后，点击重载资源即可使用。</div>{/if}
        {#if skillEditorOpen}<section class="skill-editor"><label class="field"><span>Skill 目录名称</span><Input bind:value={skillName}/></label><Textarea aria-label="Skill 源码" rows={14} bind:value={skillSource}/><Button disabled={!skillName||panel.busy||skillSaving} onclick={saveSkill}>{skillSaving?'正在保存…':'保存并重载'}</Button>{#if skillNotice}<p class={skillSaveError?'error-text':'hint'} role="status">{skillNotice}</p>{/if}</section>{/if}
        <h3 class="resource-title">提示模板</h3>{#each pi.prompts||[] as prompt}<button class="resource-button" onclick={()=>input='/'+prompt.name+' '}>/{prompt.name}<small>{prompt.description}</small></button>{/each}
        <h3 class="resource-title">扩展</h3>{#each pi.extensions||[] as extension}<p class="hint path-text">{extension.path}</p>{/each}
        {#each pi.diagnostics||[] as diagnostic}<p class="error-text">{diagnostic.message||String(diagnostic)}</p>{/each}
      {:else if drawer==='sessions'}<label class="field"><span>会话名称</span><Input placeholder={pi.name} bind:value={name}/></label><div class="row"><Button variant="outline" size="sm" disabled={panel.busy||!name} onclick={()=>act('rename',{name})}>重命名</Button><Button variant="outline" size="sm" disabled={panel.busy||!pi.file} onclick={()=>act('fork')}><GitBranch size={13}/>复制分支</Button><Button variant="ghost" size="sm" disabled={!pi.file} onclick={()=>act('export')}><Download size={13}/></Button></div>
        <Button class="compact-button" variant="outline" disabled={panel.busy||!messages.length} onclick={()=>act('compact',{text:''})}>压缩上下文</Button>
        <h3 class="resource-title">会话历史</h3>{#each pi.sessions||[] as session}<button class="session-row" class:selected={session.id===pi.id} disabled={panel.busy} onclick={()=>act('switch',{file:session.path})}><MessageSquare size={14}/><div><strong>{session.name||session.firstMessage||'新对话'}</strong><small>{new Date(session.modified).toLocaleString('zh-CN')} · {session.messageCount} 条消息</small></div></button>{/each}
        <h3 class="resource-title">当前会话分支</h3>{#each pi.entries||[] as entry}<button class="tree-entry" class:selected={entry.id===pi.leaf} disabled={panel.busy} onclick={()=>act('navigate',{entry:entry.id})}><GitBranch size={12}/><span><small>{entry.role}</small>{entry.label||'工具调用'}</span></button>{/each}
        {#if targets.length&&lastText}<h3 class="resource-title">填入其他工作流</h3>{#each targets as target}<Button variant="outline" size="sm" onclick={()=>onTransfer(target.value,lastText)}>{target.label}</Button>{/each}{/if}
      {/if}
    </div></aside>{/if}
  </div>
  <input hidden type="file" accept="image/*" multiple bind:this={imageInput} onchange={async()=>{attachments=[...attachments,...await Promise.all([...imageInput.files].map(async file=>({name:file.name,url:await readFile(file)})))];imageInput.value='';}}/>
</article>
