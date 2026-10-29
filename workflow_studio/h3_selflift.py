"""Adapt facok's SelfLift sampler to H3's in-process callbacks and local models."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
from types import FunctionType, SimpleNamespace

from moss_runner import MODELS

REPOSITORY = 'https://github.com/facok/comfyui-SelfLift.git'
REVISION = '835c3cf7919410f71f414688f049c6ca497789d0'
PACKAGE = 'workflow_selflift'
SOURCE = Path(os.environ.get('WORKFLOW_SELFLIFT_ROOT',
              str(Path(os.environ.get('WORKFLOW_WORKSPACE', '.'))/'.cache/workflow-studio/selflift')))


def upscaler_files():
    root = MODELS/'latent_upscale_models'
    root.mkdir(parents=True, exist_ok=True)
    return sorted(path.relative_to(root).as_posix() for path in root.rglob('*')
                  if path.is_file() and path.suffix.lower() in ('.safetensors', '.pth'))


def fields():
    enabled = {'selflift_enabled':True}
    zero = {**enabled, 'selflift_mode':'zero'}
    learned = {**enabled, 'selflift_mode':'learned'}
    return [dict(area='advanced', section='SelfLift', **field) for field in [
        {'key':'selflift_enabled','label':'启用 SelfLift','type':'boolean','default':False},
        {'key':'selflift_mode','label':'升分辨率方式','type':'select','default':'zero','when':enabled,
         'hint':'H3 实验适配。VAE 校正可能平滑运动细节；本地 latent upscaler 使用 H3 专用放大模型。',
         'options':[{'label':'SelfLift-zero · VAE 校正','value':'zero'}, {'label':'本地 latent upscaler','value':'learned'}]},
        {'key':'selflift_scale','label':'低分辨率比例','type':'number','default':.5,'min':.25,'max':1,'step':.05,'when':enabled,
         'hint':'宽高分别乘此比例。提高比例可保留更多运动细节，同时增加前段计算量。'},
        {'key':'selflift_low_steps','label':'低分辨率步数占比','type':'number','default':.75,'min':.05,'max':.95,'step':.05,'when':enabled,
         'hint':'降低占比可为最终分辨率保留更多恢复步数，同时增加总计算量。'},
        {'key':'selflift_rho','label':'校正区域比例 ρ','type':'number','default':.6,'min':.05,'max':1,'step':.05,'when':zero},
        {'key':'selflift_w_min','label':'最小校正强度','type':'number','default':1,'min':0,'max':1,'step':.05,'when':zero},
        {'key':'selflift_w_max','label':'最大校正强度','type':'number','default':1,'min':0,'max':1,'step':.05,'when':zero},
        {'key':'selflift_upscaler','label':'本地 latent upscaler','type':'select','default':'','options':upscaler_files(),'when':learned},
        {'key':'selflift_upscaler_unload','label':'放大后卸载 upscaler','type':'boolean','default':False,'when':learned},
    ]]


def validate(params):
    if params['sampler'] != 'euler':
        raise ValueError('SelfLift 使用标准 Euler 采样器。')
    if int(params['steps']) < 2:
        raise ValueError('SelfLift 两阶段采样至少需要 2 步。')
    if params.get('selflift_mode', 'zero') == 'learned':
        path = MODELS/'latent_upscale_models'/params.get('selflift_upscaler', '')
        if not path.is_file():
            raise FileNotFoundError('缺少本地 latent upscaler 文件：'+str(path))


def prepare(ctx):
    if PACKAGE+'.nodes' in sys.modules:
        return sys.modules[PACKAGE+'.nodes']
    if not (SOURCE/'nodes.py').is_file():
        ctx.status('准备 SelfLift 采样代码…')
        SOURCE.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['git','clone','--no-checkout','--filter=blob:none',REPOSITORY,str(SOURCE)],check=True,capture_output=True,text=True)
        subprocess.run(['git','-C',str(SOURCE),'fetch','--depth','1','origin',REVISION],check=True,capture_output=True,text=True)
        subprocess.run(['git','-C',str(SOURCE),'checkout','--detach','FETCH_HEAD'],check=True,capture_output=True,text=True)
    import folder_paths
    folder_paths.add_model_folder_path('latent_upscale_models',str(MODELS/'latent_upscale_models'),is_default=True)
    spec = importlib.util.spec_from_file_location(PACKAGE,SOURCE/'__init__.py',submodule_search_locations=[str(SOURCE)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[PACKAGE] = module
    spec.loader.exec_module(module)
    return sys.modules[PACKAGE+'.nodes']


def sample(model, positive, negative, vae, latent, params, seed, callback, ctx):
    import comfy.samplers
    nodes = prepare(ctx)
    steps = int(params['steps'])
    transition = max(1,min(steps-1,int(steps*float(params.get('selflift_low_steps',.75))+.5)))
    scale = float(params.get('selflift_scale',.5))
    learned = params.get('selflift_mode','zero') == 'learned'
    rho = 0 if learned else float(params.get('selflift_rho',.6))
    if not learned and (rho <= 0 or float(params.get('selflift_w_max',1)) <= 0):
        raise ValueError('SelfLift-zero 需要正数的校正区域比例和校正强度。')
    sampling = model.get_model_object('model_sampling')
    sigmas = (comfy.samplers.beta_scheduler(sampling,steps,alpha=.5,beta=.7) if params['scheduler']=='beta57'
              else comfy.samplers.calculate_sigmas(sampling,params['scheduler'],steps))
    lifter = None
    if learned:
        lifter = lambda value,size: nodes.h3_upscaler.learned_latent_lift(
            value,size,params['selflift_upscaler'],force_unload=bool(params.get('selflift_upscaler_unload',False)))
    high_model = None
    from h3_spark import apply as apply_spark, supported as spark_supported
    attention = params.get('attention', 'auto')
    if attention == 'spark' or (attention == 'auto' and spark_supported()):
        # Each Comfy sample cleans up Spark's controller. Repatch the high stage
        # with only the warmup evaluations left in the complete schedule.
        high_model = apply_spark(model, params, ctx, start_step=transition)

    stage_labels = {'low_resolution':'SelfLift低分辨率', 'transition':'SelfLift升分辨率',
                    'high_resolution':'SelfLift高分辨率'}

    class StageTimer(nodes._StageTimer):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.durations = []

        def mark(self, label):
            previous = self.previous
            super().mark(label)
            self.durations.append(round(self.previous-previous, 3))

        def finish(self):
            super().finish()
            label = stage_labels[self.stage]
            ctx.metadata(**{label+'秒':round(self._now()-self.started, 3)})
            if self.stage == 'high_resolution':
                ctx.metadata(**{label+'每步秒':self.durations})

    # Give this invocation its own callback factory; Comfy's module stays shared.
    original = nodes.progressive_sample
    scope = {**original.__globals__, '_StageTimer':StageTimer,
             'latent_preview':SimpleNamespace(prepare_callback=lambda *_:callback)}
    progressive = FunctionType(original.__code__,scope,original.__name__,original.__defaults__,original.__closure__)
    video = latent['samples'].tensors[0] if latent['samples'].is_nested else latent['samples']
    height,width = video.shape[-2:]
    ctx.metadata(SelfLift='本地 latent upscaler' if learned else 'SelfLift-zero',
        SelfLift步数=f'{transition} + {steps-transition}',
        SelfLift分辨率=f'{max(2,round(width*scale/2)*2)*16}×{max(2,round(height*scale/2)*2)*16} → {width*16}×{height*16}')
    result = progressive(model,positive,negative,vae,latent,comfy.samplers.sampler_object('euler'),sigmas,seed,
        float(params['cfg']),transition,scale,rho,float(params.get('selflift_w_min',1)),float(params.get('selflift_w_max',1)),
        'nearest',latent_lifter=lifter,model_hires=high_model)
    return result['samples']


def release_upscalers():
    module = sys.modules.get(PACKAGE+'.h3_upscaler')
    values = list(module._model_cache.values()) if module else []
    if module:
        module._model_cache.clear()
    return values
