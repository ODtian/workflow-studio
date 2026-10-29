import {Type} from 'typebox';

export const WORKFLOW_TOOL_NAMES=['set_image_workflow','set_h3_timeline'];

export function createWorkflowTools(context,invoke){
  const kind=Type.Union(['image','video','audio'].map(value=>Type.Literal(value)));
  const source=Type.Union([
    Type.Object({id:Type.String({description:'Existing reference ID from the H3 catalog.'})},{additionalProperties:false}),
    Type.Object({path:Type.String({description:'Local runtime media path.'}),kind,
      name:Type.Optional(Type.String()),include_audio:Type.Optional(Type.Boolean())},{additionalProperties:false})
  ]);
  const tool=(name,label,description,parameters)=>({
    name,label,description,parameters,executionMode:'sequential',
    async execute(_id,args,signal){
      signal?.throwIfAborted();
      const result=await invoke(name,args);
      return {content:[{type:'text',text:JSON.stringify(result)}],details:result};
    }
  });
  return [
    tool('set_image_workflow','填写生图工作流',
      `Fill an image workflow's prompt and aspect ratio. Keep its current pixel area and sampling settings. Only update page parameters. Available panels: ${JSON.stringify(context.images||[])}`,
      Type.Object({workflow:Type.String({description:'Target panel ID, or a workflow filename with one open panel.'}),
        prompt:Type.String(),aspect_ratio:Type.String({description:'Width:height, for example 16:9 or 1:1.'})},{additionalProperties:false})),
    tool('set_h3_timeline','设置 H3 片段',
      `Set the H3 timeline to exactly the supplied segment list. Each segment uses the workflow's current segment_seconds; total duration is segment count times that duration. Anchor time is relative to its segment. Omitted references, LoRAs and anchors mean empty assignments for that segment. Only update page parameters. Available H3 panels and resources: ${JSON.stringify(context.h3||[])}`,
      Type.Object({workflow:Type.Optional(Type.String({description:'H3 panel ID; optional when one H3 panel is open.'})),
        segments:Type.Array(Type.Object({prompt:Type.String(),name:Type.Optional(Type.String()),
          references:Type.Optional(Type.Array(source)),
          loras:Type.Optional(Type.Array(Type.Object({name:Type.String(),strength:Type.Optional(Type.Number())},{additionalProperties:false}))),
          anchors:Type.Optional(Type.Array(Type.Object({time:Type.Number({minimum:0}),source},{additionalProperties:false}))),
          method:Type.Optional(Type.Union(['motion','tail_frame','overlap','shots'].map(value=>Type.Literal(value)))),
          context_frames:Type.Optional(Type.Integer({minimum:1})),
          audio_context_frames:Type.Optional(Type.Integer({minimum:0})),
          blend_frames:Type.Optional(Type.Integer({minimum:0})),audio:Type.Optional(Type.Boolean())
        },{additionalProperties:false}),{minItems:1})},{additionalProperties:false}))
  ];
}
