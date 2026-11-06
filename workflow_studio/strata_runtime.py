"""Official Strata 0.2.10 control and CUDA 13 DeepSeek engine packages."""
from pathlib import Path
import json
import sys
import tarfile
import urllib.request

ROOT = Path("/tmp/molab-comfy-runtime/strata")
CONTROL = ROOT / "control"
ENGINE = ROOT / "engine" / "strata-dsv41"
QWEN_ENGINE = ROOT / "qwen-engine" / "strata"
RELEASE = "https://github.com/Niko1221/Strata/releases/download/v0.2.10"
PACKAGES = (
    ("strata-control-0.1.56-linux-x86_64.tar.gz", CONTROL),
    ("strata-dsv41-0.1.56-linux-x86_64-cuda-cuda13.tar.gz", ENGINE.parent),
    ("strata-engine-0.1.56-linux-x86_64-cuda-cuda13.tar.gz", QWEN_ENGINE.parent),
)


def ensure_runtime(ctx=None):
    ROOT.mkdir(parents=True, exist_ok=True)
    for name, target in PACKAGES:
        marker = target / ".installed"
        if marker.exists():
            continue
        if ctx:
            ctx.status("下载 Strata 预编译运行时 · " + name)
        archive = ROOT / name
        urllib.request.urlretrieve(RELEASE + "/" + name, archive)
        target.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive) as bundle:
            bundle.extractall(target, filter="data")
        marker.touch()
        archive.unlink()
    ENGINE.chmod(0o755)
    QWEN_ENGINE.chmod(0o755)
    for path in (CONTROL, CONTROL / "tools"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    return CONTROL, ENGINE
