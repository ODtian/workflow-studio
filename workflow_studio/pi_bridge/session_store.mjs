import {join} from 'node:path';
import {randomUUID} from 'node:crypto';
import {mkdir,readFile,writeFile,readdir,stat} from 'node:fs/promises';
import {SessionManager} from '@earendil-works/pi-coding-agent';

const magic=Buffer.from('WFSC1\0');
export class PiSessionStore {
  constructor(cwd){this.cwd=cwd;this.protected=process.env.WORKFLOW_OBFUSCATE_CONTENT==='1';this.files=new WeakMap();this.pending=new WeakMap();}
  create(dir){return this.protected?SessionManager.inMemory(this.cwd):SessionManager.create(this.cwd,dir);}
  file(manager,dir){
    if(!this.protected)return manager.getSessionFile();
    if(!this.files.has(manager))this.files.set(manager,join(dir,manager.getSessionId()+'.jsonl'));
    return this.files.get(manager);
  }
  source(manager){return [manager.getHeader(),...manager.getEntries()].map(entry=>JSON.stringify(entry)).join('\n')+'\n';}
  async entries(file){
    const data=await readFile(file);let offset=0;
    if(data.subarray(0,magic.length).equals(magic)){offset=magic.length;for(let i=offset;i<data.length;i++)data[i]^=0xA7;}
    return data.subarray(offset).toString('utf8').trim().split('\n').map(line=>JSON.parse(line));
  }
  async open(file,dir){
    if(!this.protected)return SessionManager.open(file,dir,this.cwd);
    const manager=SessionManager.inMemory(this.cwd,undefined,await this.entries(file));this.files.set(manager,file);return manager;
  }
  async recent(dir){
    if(!this.protected)return SessionManager.continueRecent(this.cwd,dir);
    const sessions=await this.list(dir);return sessions.length?this.open(sessions[0].path,dir):this.create(dir);
  }
  async fork(manager,dir){
    if(!this.protected)return SessionManager.forkFrom(manager.getSessionFile(),this.cwd,dir);
    const header={...manager.getHeader(),id:randomUUID(),timestamp:new Date().toISOString(),parentSession:this.file(manager,dir)};
    return SessionManager.inMemory(this.cwd,undefined,[header,...manager.getEntries()]);
  }
  save(manager,dir){
    if(!this.protected)return Promise.resolve();
    const pending=(this.pending.get(manager)||Promise.resolve()).then(async()=>{
      await mkdir(dir,{recursive:true});
      const text=this.source(manager),data=Buffer.allocUnsafe(magic.length+Buffer.byteLength(text));
      magic.copy(data);data.write(text,magic.length,'utf8');
      for(let i=magic.length;i<data.length;i++)data[i]^=0xA7;
      await writeFile(this.file(manager,dir),data);
    });this.pending.set(manager,pending);return pending;
  }
  async list(dir){
    if(!this.protected)return SessionManager.list(this.cwd,dir);
    await mkdir(dir,{recursive:true});const sessions=[];
    for(const name of await readdir(dir)){
      if(!name.endsWith('.jsonl'))continue;
      const path=join(dir,name),entries=await this.entries(path),header=entries[0],info=await stat(path);
      const messages=entries.filter(entry=>entry.type==='message');
      const first=messages.find(entry=>entry.message.role==='user')?.message.content;
      sessions.push({path,id:header.id,cwd:header.cwd,name:entries.filter(entry=>entry.type==='session_info').at(-1)?.name,
        created:header.timestamp,modified:info.mtime.toISOString(),messageCount:messages.length,
        firstMessage:typeof first==='string'?first:first?.filter(part=>part.type==='text').map(part=>part.text).join('')||''});
    }return sessions.sort((a,b)=>b.modified.localeCompare(a.modified));
  }
}
