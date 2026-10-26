export const FPS=24, MAX_FRAMES=362;
export const frameCount=seconds=>Math.round(Number(seconds)*FPS);
export const seconds=frames=>frames/FPS;
export const uid=()=>crypto.randomUUID();
export const methodNames={motion:'运动上下文',tail_frame:'末帧续写',overlap:'上下文＋淡化',shots:'独立分镜'};
const copy=value=>JSON.parse(JSON.stringify(value));
const grid=frames=>Math.max(5,frames)+((5-Math.max(5,frames))%17+17)%17;

export function planTimeline(timeline){
  let start=0;
  return (timeline.clips||[]).map((clip,index,clips)=>{
    const frames=frameCount(clip.duration),available=index?Math.min(Number(clip.context_frames),frameCount(clips[index-1].duration)):0;
    const carry=!index||clip.method==='shots'?0:clip.method==='tail_frame'?1:[124,107,90,73,56,39,22,5,1].find(n=>n<=available);
    const sample=grid(frames+carry),result={...clip,index,start:seconds(start),end:seconds(start+frames),frames,carry,sample,padding:sample-carry-frames,sampleStart:seconds(start-carry),sampleEnd:seconds(start-carry+sample)};
    start+=frames;return result;
  });
}
export function clipDefaults(values,id=uid()){
  return {id,name:'分段',duration:5,prompt:values.prompt||'',method:values.long_video==='single'?'tail_frame':values.long_video||'motion',context_frames:Number(values.context_frames||22),audio_context_frames:Number(values.audio_context_frames??18),blend_frames:6,audio:values.audio??true};
}
export function initialTimeline(values){
  const total=frameCount(values.duration),technique=values.long_video||'motion',chunk=technique==='single'?362:frameCount(values.segment_seconds||5),prompts=(values.shot_prompts||'').split(/\n\s*\n/).filter(s=>s.trim()),boundaries=technique==='shots'&&prompts.length?Array.from({length:prompts.length+1},(_,i)=>Math.round(i*total/prompts.length)):[0,total];
  const clips=[];let start=0;
  while(start<total){
    const shot=boundaries.slice(1).findIndex(end=>start<end),shotEnd=boundaries[shot+1],atShot=start===boundaries[shot];
    const overlap=clips.length?(technique==='shots'&&atShot?0:Math.min(['motion','overlap','shots'].includes(technique)?Number(values.context_frames||22):1,start)):0;
    let sample=grid(Math.min(shotEnd-start+overlap,chunk+overlap,362));if(sample>362)sample-=17;
    const frames=Math.min(shotEnd-start,sample-overlap),clip=clipDefaults(values);
    clip.name=`分段 ${clips.length+1}`;clip.duration=seconds(frames);
    if(technique==='shots'){clip.method=atShot?'shots':'motion';clip.prompt=[values.prompt,prompts[shot]].filter(Boolean).join('\n');}
    clips.push(clip);start+=frames;
  }
  return {version:1,clips,resources:[...(values.references||[]).map(item=>({id:item.id,kind:'reference',segments:clips.map(c=>c.id)})),...(values.loras||[]).map(item=>({id:item.id,kind:'lora',segments:clips.map(c=>c.id),weights:Object.fromEntries(clips.map(c=>[c.id,item.strength]))}))]};
}
export function resourceRuns(timeline,resource){
  const plan=planTimeline(timeline),runs=[];
  for(const clip of plan){if(!resource.segments.includes(clip.id))continue;const last=runs.at(-1);if(last&&last.last===clip.index-1){last.last=clip.index;last.end=clip.end;last.ids.push(clip.id);}else runs.push({first:clip.index,last:clip.index,start:clip.start,end:clip.end,ids:[clip.id]});}
  return runs;
}
export function mergeClips(timeline,first,last){
  const next=copy(timeline),chosen=next.clips.slice(first,last+1),ids=new Set(chosen.map(c=>c.id)),merged={...chosen[0],duration:seconds(chosen.reduce((n,c)=>n+frameCount(c.duration),0)),prompt:[...new Set(chosen.map(c=>c.prompt).filter(Boolean))].join('\n')};
  next.clips.splice(first,chosen.length,merged);
  const segment=planTimeline(next)[first];
  if(segment.sample>MAX_FRAMES)throw new Error(`合并后的计算窗口为 ${segment.sample} 帧；单次上限 ${MAX_FRAMES} 帧`);
  for(const resource of next.resources){const active=chosen.find(c=>resource.segments.includes(c.id));resource.segments=[...new Set(resource.segments.map(id=>ids.has(id)?merged.id:id))];if(resource.kind==='lora'&&active){const weight=resource.weights[active.id];for(const id of ids)delete resource.weights[id];resource.weights[merged.id]=weight;}}
  return next;
}
export function splitClip(timeline,id,time){
  const next=copy(timeline),plan=planTimeline(next),index=plan.findIndex(c=>c.id===id),clip=next.clips[index],frames=frameCount(time-plan[index].start);
  if(frames<1||frames>=frameCount(clip.duration))return next;
  const right={...clip,id:uid(),name:clip.name+' · 续',duration:seconds(frameCount(clip.duration)-frames)};
  clip.duration=seconds(frames);next.clips.splice(index+1,0,right);
  for(const resource of next.resources)if(resource.segments.includes(id)){resource.segments.push(right.id);if(resource.kind==='lora')resource.weights[right.id]=resource.weights[id];}
  return next;
}
export function reorderClip(timeline,id,index){const next=copy(timeline),source=next.clips.findIndex(c=>c.id===id),[moving]=next.clips.splice(source,1);next.clips.splice(index,0,moving);return next;}
export function moveBoundary(timeline,index,time){
  const next=copy(timeline),plan=planTimeline(next),left=plan[index-1],right=plan[index];
  const at=Math.max(frameCount(left.start)+1,Math.min(frameCount(right.end)-1,frameCount(time)));
  next.clips[index-1].duration=seconds(at-frameCount(left.start));next.clips[index].duration=seconds(frameCount(right.end)-at);
  if(planTimeline(next).some(c=>c.sample>MAX_FRAMES))return timeline;
  return next;
}
