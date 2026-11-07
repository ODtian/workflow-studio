"""Carry widget code through the ESM channel on authenticated notebook hosts."""
import base64


def embed_widget_modules():
    from marimo._messaging.notification import EsmSpec, _normalize_esm_url

    original = EsmSpec.from_esm
    if getattr(original, "studio_embedded", False):
        return

    def from_esm(source):
        if _normalize_esm_url(source) is None:
            source = "data:text/javascript;base64," + base64.b64encode(source.encode("utf-8")).decode("ascii")
        return original(source)

    from_esm.studio_embedded = True
    EsmSpec.from_esm = staticmethod(from_esm)
