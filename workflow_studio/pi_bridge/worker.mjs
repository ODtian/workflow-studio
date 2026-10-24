import {join} from 'node:path';
import {mkdir} from 'node:fs/promises';
import {createAssistantMessageEventStream, getCurrentSystemPrompt} from '@earendil-works/pi-ai';
import {
  createAgentSession, createExtensionRuntime, ModelRuntime, SessionManager, SettingsManager
} from '@earendil-works/pi-coding-agent';

const send = value => process.stdout.write(JSON.stringify(value) + '\n');
const agentDir = process.env.WORKFLOW_PI_DIR;
await mkdir(agentDir, {recursive:true});
const runtime = await ModelRuntime.create({
  authPath:join(agentDir, 'auth.json'), modelsPath:null, refreshOnCreate:false
});
const pending = new Map();
const sessions = new Map();
let sequence = 0;
let activeSession;
const usage = () => ({input:0, output:0, cacheRead:0, cacheWrite:0, totalTokens:0,
  cost:{input:0, output:0, cacheRead:0, cacheWrite:0, total:0}});

function content(value) {
  if (typeof value === 'string') return [{type:'text', text:value}];
  return value.map(item => {
    if (item.type === 'image_url') {
      const [header, data] = item.image_url.url.split(',', 2);
      return {type:'image', mimeType:header.slice(5).split(';')[0], data};
    }
    return item;
  });
}

function nativeMessages(context) {
  const system = getCurrentSystemPrompt(context.messages);
  return [...(system ? [{role:'system', content:system}] : []), ...context.messages.filter(message => message.role !== 'system').map(message => ({
    role:message.role,
    content:typeof message.content === 'string' ? message.content : message.content.flatMap(item => {
      if (item.type === 'text') return [{type:'text', text:item.text}];
      if (item.type === 'image') return [{type:'image_url', image_url:{url:`data:${item.mimeType};base64,${item.data}`}}];
      return [];
    })
  }))];
}

function nativeStream(model, context) {
  const stream = createAssistantMessageEventStream();
  const id = ++sequence;
  const message = {role:'assistant', api:model.api, provider:model.provider, model:model.id,
    content:[], usage:usage(), stopReason:'stop', timestamp:Date.now()};
  const indexes = new Map();
  stream.push({type:'start', partial:message});
  pending.set(id, record => {
    if (record.type === 'model_delta') {
      for (const [name, type, field] of [['reasoning','thinking','thinking'],['content','text','text']]) {
        const next = record[name] || '';
        if (!next && !indexes.has(name)) continue;
        if (!indexes.has(name)) {
          indexes.set(name, message.content.length);
          message.content.push({type, [field]:''});
          stream.push({type:`${type}_start`, contentIndex:indexes.get(name), partial:message});
        }
        const index = indexes.get(name);
        const delta = next.slice(message.content[index][field].length);
        message.content[index][field] = next;
        if (delta) stream.push({type:`${type}_delta`, contentIndex:index, delta, partial:message});
      }
    } else {
      pending.delete(id);
      if (record.type === 'model_error') {
        message.stopReason = 'error';
        message.errorMessage = record.error;
        stream.push({type:'error', reason:'error', error:message});
      } else {
        for (const [name, index] of indexes) {
          const type = name === 'content' ? 'text' : 'thinking';
          stream.push({type:`${type}_end`, contentIndex:index, content:message.content[index][type], partial:message});
        }
        message.usage.output = record.outputTokens;
        message.usage.totalTokens = record.outputTokens;
        stream.push({type:'done', reason:'stop', message});
      }
      stream.end();
    }
  });
  send({type:'model_request', id, messages:nativeMessages(context)});
  return stream;
}

async function prompt(request) {
  const config = request.config;
  runtime.registerProvider('notebook', {
    name:'Notebook llama.cpp', baseUrl:'stdio://notebook', apiKey:'notebook-local',
    api:'notebook-llama', streamSimple:nativeStream,
    models:[{id:config.model, name:config.model, reasoning:true, input:['text','image'],
      contextWindow:Number(config.n_ctx), maxTokens:Number(config.max_tokens),
      cost:{input:0,output:0,cacheRead:0,cacheWrite:0}}]
  });
  const model = runtime.getModel('notebook', config.model);
  const messages = request.messages;
  const signature = JSON.stringify([config.model,config.n_ctx,config.max_tokens,config.system_prompt,config.thinking]);
  let cached = sessions.get(request.conversationId);
  if (cached && (cached.signature !== signature || JSON.stringify(cached.nodes) !== JSON.stringify(request.nodes.slice(0,-2)))) {
    cached.session.dispose();
    cached = undefined;
  }
  const loader = {
    getExtensions:() => ({extensions:[], errors:[], runtime:createExtensionRuntime()}),
    getSkills:() => ({skills:[], diagnostics:[]}), getPrompts:() => ({prompts:[], diagnostics:[]}),
    getThemes:() => ({themes:[], diagnostics:[]}), getAgentsFiles:() => ({agentsFiles:[]}),
    getSystemPrompt:() => config.system_prompt, getSystemPromptSource:() => undefined,
    getAppendSystemPrompt:() => [], getAppendSystemPromptSources:() => [],
    extendResources:() => {}, reload:async () => {}
  };
  if (!cached) {
    const manager = SessionManager.inMemory(process.cwd());
    for (const message of messages.slice(0, -1)) {
      const entry = {role:message.role, content:content(message.content), timestamp:Date.now()};
      if (entry.role === 'assistant') Object.assign(entry, {
        api:model.api, provider:model.provider, model:model.id, usage:usage(), stopReason:'stop'
      });
      manager.appendMessage(entry);
    }
    const {session} = await createAgentSession({
      cwd:process.cwd(), agentDir, model, modelRuntime:runtime,
      thinkingLevel:config.thinking === 'on' ? 'medium' : 'off', tools:[],
      sessionManager:manager, resourceLoader:loader,
      settingsManager:SettingsManager.inMemory({retry:{enabled:false}})
    });
    cached = {session, manager, signature, nodes:[]};
    sessions.set(request.conversationId, cached);
  }
  const {session, manager} = cached;
  activeSession = session;
  send({type:'session', id:manager.getSessionId()});
  const unsubscribe = session.subscribe(event => send({type:'event', event}));
  try {
    const latest = content(messages.at(-1).content);
    await session.prompt(latest.filter(item => item.type === 'text').map(item => item.text).join('\n'), {
      images:latest.filter(item => item.type === 'image')
    });
    const last = session.messages.at(-1);
    if (last?.stopReason === 'error') throw new Error(last.errorMessage);
    cached.nodes = request.nodes;
    send({type:'result', content:session.getLastAssistantText() || ''});
  } finally {
    unsubscribe();
    activeSession = undefined;
  }
}

let buffer = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => {
  buffer += chunk;
  let end;
  while ((end = buffer.indexOf('\n')) !== -1) {
    const line = buffer.slice(0, end);
    buffer = buffer.slice(end + 1);
    if (!line) continue;
    const record = JSON.parse(line);
    if (record.type.startsWith('model_')) pending.get(record.id)?.(record);
    else if (record.type === 'abort') activeSession?.abort();
    else if (record.type === 'prompt') prompt(record).catch(error => send({type:'result', error:error.stack || String(error)}));
  }
});
process.stdin.on('end', () => process.exit());
send({type:'ready', version:'1.4.0'});
