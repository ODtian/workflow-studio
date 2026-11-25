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


def _colab_workflow_routes(user_manager):
    add_routes = user_manager.add_routes

    def add_with_workflow_paths(routes):
        add_routes(routes)
        # Colab can decode a slash inside an encoded workflow path before routing.
        # Reuse the userdata handlers so path checks and save semantics stay identical.
        aliases = {
            "/userdata/{file}/move/{dest}": r"/userdata/{file:workflows/.+?\.json}/move/{dest:workflows/.+\.json}",
            "/userdata/{file}": r"/userdata/{file:workflows/.+\.json}",
        }
        native_routes = tuple(routes)
        for original, alias in aliases.items():
            for route in native_routes:
                if isinstance(route, web.RouteDef) and route.path == original:
                    routes.route(route.method, alias)(route.handler, **route.kwargs)

    user_manager.add_routes = add_with_workflow_paths


origin = os.environ.get("WORKFLOW_STUDIO_COMFY_ORIGIN")
if origin:
    server = PromptServer.instance
    middlewares = server.app.middlewares
    for index, middleware in enumerate(middlewares):
        if middleware.__name__ == "origin_only_middleware":
            middlewares[index] = _colab_origin_guard(middleware, origin)
            break
    else:
        raise RuntimeError("Could not find ComfyUI's origin middleware")
    _colab_workflow_routes(server.user_manager)

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
