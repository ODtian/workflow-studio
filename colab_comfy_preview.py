"""Keep ComfyUI's request checks compatible with a Colab preview."""
import logging
import os
from pathlib import Path
from urllib.parse import urlsplit

from aiohttp import web
from server import PromptServer


def _colab_origin_guard(default_guard, origin):
    public_host = urlsplit(origin).netloc

    @web.middleware
    async def guard(request, handler):
        headers = request.headers
        # Colab opens the front page as a user-initiated cross-site navigation.
        if (request.method == "GET" and request.path == "/" and not request.query_string
                and headers.get("Sec-Fetch-Dest") == "document"
                and headers.get("Sec-Fetch-Mode") == "navigate"
                and headers.get("Sec-Fetch-User") == "?1"
                and headers.get("Origin") in (None, origin)):
            return await handler(request)

        # The reverse proxy can forward a loopback Host. Check same-origin
        # requests using the public Host that the browser reached.
        if headers.get("Sec-Fetch-Site") == "same-origin" and headers.get("Origin") == origin:
            forwarded = headers.copy()
            forwarded["Host"] = public_host
            return await default_guard(request.clone(headers=forwarded), handler)

        return await default_guard(request, handler)

    return guard


origin = os.environ.get("WORKFLOW_STUDIO_COMFY_ORIGIN")
if origin:
    middlewares = PromptServer.instance.app.middlewares
    for index, middleware in enumerate(middlewares):
        if middleware.__name__ == "origin_only_middleware":
            middlewares[index] = _colab_origin_guard(middleware, origin)
            break
    else:
        raise RuntimeError("Could not find ComfyUI's origin middleware")

manifest = os.environ.get("WORKFLOW_STUDIO_COMFY_PLUGINS")
if manifest:
    import folder_paths
    from comfy_plugins import remember_plugins

    try:
        nodes = Path(folder_paths.__file__).resolve().parent / "custom_nodes"
        remember_plugins(nodes, Path(manifest))
    except (OSError, ValueError):
        logging.exception("ComfyUI 插件清单保存失败")

NODE_CLASS_MAPPINGS = {}
