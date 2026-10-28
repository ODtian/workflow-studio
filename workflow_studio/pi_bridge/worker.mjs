import {join, dirname, basename} from 'node:path';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {createAssistantMessageEventStream, getCurrentSystemPrompt, getCurrentTools} from '@earendil-works/pi-ai';
import {createAgentSession, DefaultResourceLoader, ModelRuntime, SessionManager, SettingsManager, parseSkillBlock} from '@earendil-works/pi-coding-agent';
import {PiSessionStore} from './session_store.mjs';
const send=value=>process.stdout.write(JSON.stringify(value)+'\n');
const cwd=process.cwd(), agentDir=process.env.WORKFLOW_PI_DIR;
const storage=new PiSessionStore(cwd),sessionRoot=process.env.WORKFLOW_PI_SESSIONS||join(agentDir,'sessions');
await mkdir(agentDir,{recursive:true});
const runtime=await ModelRuntime.create({authPath:join(agentDir,'auth.json'),modelsPath:null,refreshOnCreate:false});
const pending=new Map(), sessions=new Map();let sequence=0;
const usage=()=>({input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}});
function displayText(text){const skill=parseSkillBlock(text);return skill?`/skill:${skill.name}${skill.userMessage?' '+skill.userMessage:''}`:text;}
function displayMessage(message){
  if(message.role!=='user')return message;
  return {...message,content:typeof message.content==='string'?displayText(message.content):message.content.map(part=>part.type==='text'?{...part,text:displayText(part.text)}:part)};
}
function nativeMessages(context) {
  const system=getCurrentSystemPrompt(context.messages);
  return [...(system?[{role:'system',content:system}]:[]),...context.messages.filter(m=>m.role!=='system').map(m=>{
    const parts=typeof m.content==='string'?[{type:'text',text:m.content}]:m.content;
    const images=parts.filter(p=>p.type==='image').map(p=>({type:'image_url',image_url:{url:`data:${p.mimeType};base64,${p.data}`}}));
    const text=parts.filter(p=>p.type==='text').map(p=>p.text).join('\n');
    if(m.role==='toolResult')return {role:'tool',tool_call_id:m.toolCallId,content:images.length?[...images,{type:'text',text}]:text};
    const calls=parts.filter(p=>p.type==='toolCall').map(p=>({id:p.id,type:'function',function:{name:p.name,arguments:JSON.stringify(p.arguments)}}));
    return {role:m.role,content:images.length?[...images,{type:'text',text}]:text,...(calls.length?{tool_calls:calls}:{})};
  })];
}
function nativeStream(model,context) {
  const stream=createAssistantMessageEventStream(),id=++sequence;
  const message={role:'assistant',api:model.api,provider:model.provider,model:model.id,content:[],usage:usage(),stopReason:'stop',timestamp:Date.now()};
  const indexes=new Map();stream.push({type:'start',partial:message});
  pending.set(id,record=>{
    if(record.type==='model_delta') {
      for(const [name,type,field] of [['reasoning','thinking','thinking'],['content','text','text']]) {
        const next=record[name]||'';if(!next&&!indexes.has(name))continue;
        if(!indexes.has(name)){indexes.set(name,message.content.length);message.content.push({type,[field]:''});stream.push({type:`${type}_start`,contentIndex:indexes.get(name),partial:message});}
        const index=indexes.get(name),delta=next.slice(message.content[index][field].length);message.content[index][field]=next;
        if(delta)stream.push({type:`${type}_delta`,contentIndex:index,delta,partial:message});
      }return;
    }
    pending.delete(id);
    if(record.type==='model_error'){message.stopReason='error';message.errorMessage=record.error;stream.push({type:'error',reason:'error',error:message});}
    else {
      for(const [name,index] of indexes){const type=name==='content'?'text':'thinking';stream.push({type:`${type}_end`,contentIndex:index,content:message.content[index][type],partial:message});}
      for(const call of record.calls||[]){const index=message.content.length;message.content.push({type:'toolCall',...call});stream.push({type:'toolcall_start',contentIndex:index,partial:message});stream.push({type:'toolcall_delta',contentIndex:index,delta:JSON.stringify(call.arguments),partial:message});stream.push({type:'toolcall_end',contentIndex:index,toolCall:message.content[index],partial:message});}
      message.usage={...usage(),input:record.inputTokens||0,output:record.outputTokens,totalTokens:(record.inputTokens||0)+record.outputTokens};
      message.stopReason=record.calls?.length?'toolUse':'stop';stream.push({type:'done',reason:message.stopReason,message});
    }stream.end();
  });
  send({type:'model_request',id,messages:nativeMessages(context),tools:getCurrentTools(context.messages).map(t=>({type:'function',function:{name:t.name,description:t.description,parameters:t.parameters}}))});return stream;
}
function register(config){runtime.registerProvider('notebook',{name:'Notebook llama.cpp',baseUrl:'stdio://notebook',apiKey:'notebook-local',api:'notebook-llama',streamSimple:nativeStream,models:[{id:config.model,name:config.model,reasoning:true,input:['text','image'],contextWindow:Number(config.n_ctx),maxTokens:Number(config.max_tokens),cost:{input:0,output:0,cacheRead:0,cacheWrite:0}}]});return runtime.getModel('notebook',config.model);}
async function create(panel,config,manager){
  const settings=SettingsManager.inMemory({retry:{enabled:false}});
  const loader=new DefaultResourceLoader({cwd,agentDir,settingsManager:settings,appendSystemPrompt:[config.system_prompt||'']});await loader.reload();
  const {session}=await createAgentSession({cwd,agentDir,model:register(config),modelRuntime:runtime,thinkingLevel:config.thinking==='on'?'medium':'off',tools:['read','bash','edit','write','grep','find','ls'],sessionManager:manager,resourceLoader:loader,settingsManager:settings});
  await session.bindExtensions({});
  if(config.saved_tools)session.setActiveToolsByName(config.saved_tools);
  const item={session,manager,config,dir:join(sessionRoot,panel)};
  session.subscribe(event=>{if(storage.compressed&&event.type==='message_end')storage.save(manager,item.dir).catch(error=>{item.saveError=error;});});
  sessions.set(panel,item);return item;
}
async function ensure(request){
  let item=sessions.get(request.panel);
  if(!item){const dir=join(sessionRoot,request.panel),saved='saved_session' in request.config;item=await create(request.panel,request.config,await(saved?(request.config.saved_session?storage.open(request.config.saved_session,dir):storage.create(dir)):storage.recent(dir)));}
  if(JSON.stringify(item.config)!==JSON.stringify(request.config)){
    if(item.config.system_prompt!==request.config.system_prompt){item.session.dispose();return create(request.panel,request.config,item.manager);}
    await item.session.setModel(register(request.config));item.session.setThinkingLevel(request.config.thinking==='on'?'medium':'off');item.config=request.config;
  }return item;
}
async function snapshot(item){
  const {session,manager}=item,loader=session.resourceLoader;
  return {id:manager.getSessionId(),name:manager.getSessionName()||'新对话',file:storage.file(manager,item.dir),messages:session.messages.map(displayMessage),
    entries:manager.getEntries().filter(e=>e.type==='message').map(e=>{const message=displayMessage(e.message);return {id:e.id,parentId:e.parentId,role:message.role,timestamp:message.timestamp,label:typeof message.content==='string'?message.content.slice(0,75):message.content.filter(p=>p.type==='text').map(p=>p.text).join('').slice(0,75)};}),
    leaf:manager.getLeafId(),stats:session.getSessionStats(),sessions:await storage.list(item.dir),tools:session.getAllTools(),activeTools:session.getActiveToolNames(),skills:loader.getSkills().skills,prompts:loader.getPrompts().prompts,
    extensions:loader.getExtensions().extensions.map(e=>({path:e.resolvedPath||e.path})),diagnostics:[...loader.getSkills().diagnostics,...loader.getPrompts().diagnostics,...loader.getExtensions().errors]};
}
async function command(request){
  let item=await ensure(request);const {action}=request;let editor;
  if(action==='abort'){await item.session.abort();return;}
  if(action==='steer'||action==='follow_up')await item.session[action==='steer'?'steer':'followUp'](request.text);
  else if(['new','switch','fork'].includes(action)){
    const manager=await(action==='new'?storage.create(item.dir):action==='switch'?storage.open(request.file,item.dir):storage.fork(item.manager,item.dir));
    item.session.dispose();item=await create(request.panel,request.config,manager);
  }else if(action==='rename')item.manager.appendSessionInfo(request.name);
  else if(action==='navigate'){
    const target=item.manager.getEntry(request.entry);
    const result=await item.session.navigateTree(request.entry,{summarize:false});
    if(!result.cancelled&&target.type==='message'&&target.message.role==='user'){
      const parts=typeof target.message.content==='string'?[{type:'text',text:target.message.content}]:target.message.content;
      editor={text:displayText(result.editorText??parts.filter(p=>p.type==='text').map(p=>p.text).join('\n')),images:parts.filter(p=>p.type==='image')};
    }
  }
  else if(action==='tools')item.session.setActiveToolsByName(request.tools);
  else if(action==='reload')await item.session.reload();
  else if(action==='read_skill')send({type:'skill',request:request.request,path:request.path,source:await readFile(request.path,'utf8')});
  else if(action==='save_skill'){const path=join(cwd,'.pi','skills',basename(request.name),'SKILL.md');await mkdir(dirname(path),{recursive:true});await writeFile(path,request.source);await item.session.reload();}
  else if(action==='export')send({type:'export',request:request.request,name:'pi-session.jsonl',source:storage.compressed?storage.source(item.manager):await readFile(item.manager.getSessionFile(),'utf8')});
  else if(action==='prompt'||action==='compact'){
    const off=item.session.subscribe(event=>send({type:'event',request:request.request,event:event.message?{...event,message:displayMessage(event.message)}:event}));
    try{
      if(action==='compact')await item.session.compact(request.text);
      else await item.session.prompt(request.text,{images:(request.images||[]).map(image=>{const [header,data]=image.url.split(',',2);return {type:'image',mimeType:header.slice(5).split(';')[0],data};})});
      const last=item.session.messages.at(-1);if(last?.stopReason==='error')throw new Error(last.errorMessage);
    }finally{off();}
  }
  await storage.save(item.manager,item.dir);
  send({type:'result',request:request.request,snapshot:{...await snapshot(item),...(editor?{editor}:{})},content:item.session.getLastAssistantText()||''});
}
let buffer='';process.stdin.setEncoding('utf8');process.stdin.on('data',chunk=>{
  buffer+=chunk;let end;while((end=buffer.indexOf('\n'))!==-1){const line=buffer.slice(0,end);buffer=buffer.slice(end+1);if(!line)continue;const record=JSON.parse(line);
    if(record.type.startsWith('model_'))pending.get(record.id)?.(record);else command(record).catch(async error=>{const item=sessions.get(record.panel);send({type:'result',request:record.request,error:error.stack||String(error),...(item?{snapshot:await snapshot(item)}:{})});});}
});process.stdin.on('end',()=>process.exit());send({type:'ready',version:'1.4.0'});
