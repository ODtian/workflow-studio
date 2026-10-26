"""Explicit release of the model caches owned by each workflow backend."""
import gc
import sys


def workflow_group(name):
    return {'moss_image.py':'moss', 'minimax_h3.py':'h3', 'llama_cpp.py':'llama'}.get(name,'diffusers')


def release(group='all'):
    targets = set()
    if group in ('all','llama') and 'llama_runner' in sys.modules:
        sys.modules['llama_runner'].release()
    moss = sys.modules.get('moss_runner')
    h3 = sys.modules.get('h3_runner')
    if group in ('all','moss') and moss is not None:
        for value in moss._loaded or ():
            patcher = getattr(value, 'patcher', value)
            targets.add(id(patcher.model))
        moss._loaded = moss._loaded_key = None
        moss._adapted = moss._adapted_key = None
        moss._compiled = moss._compiled_key = None
        moss._conditioning.clear()
    if group in ('all','h3') and h3 is not None:
        from h3_selflift import release_upscalers
        for patcher in release_upscalers():
            targets.add(id(patcher.model))
        for value in h3._components.values():
            patcher = getattr(value, 'patcher', value)
            targets.add(id(patcher.model))
        h3._components.clear()
        h3._lora_models.clear()
        h3._conditioning.clear()
    diffusion = sys.modules.get('diffusers_runner')
    if group in ('all','diffusers') and diffusion is not None:
        if diffusion._pipeline is not None:
            diffusion._pipeline.to('cpu')
        diffusion._pipeline = diffusion._cache_key = None
    if 'comfy.model_management' in sys.modules:
        mm = sys.modules['comfy.model_management']
        keep = [] if group == 'all' else [loaded for loaded in mm.current_loaded_models if id(loaded.model.model) not in targets]
        mm.free_memory(1e30, mm.get_torch_device(), keep_loaded=keep)
    gc.collect()
    if 'torch' in sys.modules:
        torch = sys.modules['torch']
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    return group
