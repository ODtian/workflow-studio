"""Keep generated originals and their parameters beside the Studio workspace."""
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

from PIL import Image


class ImageHistory:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.thumbnails = self.directory / "thumbnails"
        self.thumbnails.mkdir(exist_ok=True)
        self.index_path = self.directory / "index.json"
        self.entries = json.loads(self.index_path.read_text(encoding="utf-8")) if self.index_path.exists() else []
        self.persist_image = None
        self.persist_index = None

    def save(self):
        self.index_path.write_text(json.dumps(self.entries, ensure_ascii=False, indent=2), encoding="utf-8")
        if self.persist_index:
            self.persist_index()

    def add(self, source, metadata):
        source = Path(source)
        original = self.directory / source.name
        shutil.copy2(source, original)
        with Image.open(original) as image:
            entry = {"name": source.name, "kind": "image", "workflow": metadata["workflow"],
                     "width": image.width, "height": image.height, "bytes": original.stat().st_size,
                     "created_at": datetime.fromtimestamp(source.stat().st_mtime, timezone.utc).isoformat(),
                     "params": metadata["params"], "run_info": metadata.get("run_info", {})}
            thumbnail = image.convert("RGB")
            thumbnail.thumbnail((240, 240))
            thumbnail.save(self.thumbnails / (source.stem + ".jpg"), "JPEG", quality=75)
        self.entries.append(entry)
        if self.persist_image:
            self.persist_image(source.name)
        return entry

    def import_directory(self, directory):
        known = {entry["name"] for entry in self.entries}
        for source in sorted(Path(directory).glob("*.png")):
            if source.name in known:
                continue
            with Image.open(source) as image:
                encoded = image.info.get("workflow_studio")
            if encoded:
                self.add(source, json.loads(encoded))
        self.save()

    def add_video(self, source, video, metadata):
        source = Path(source)
        original = self.directory / source.name
        shutil.copy2(source, original)
        entry = {"name": source.name, "kind": "video", "workflow": metadata["workflow"],
                 **{key: video[key] for key in ("width", "height", "fps", "frames", "duration", "segments")},
                 "bytes": original.stat().st_size,
                 "created_at": datetime.fromtimestamp(source.stat().st_mtime, timezone.utc).isoformat(),
                 "params": metadata["params"], "run_info": metadata["run_info"]}
        thumbnail = video["poster"].convert("RGB")
        thumbnail.thumbnail((240, 240))
        thumbnail.save(self.thumbnails / (source.stem + ".jpg"), "JPEG", quality=75)
        self.entries.append(entry)
        if self.persist_image:
            self.persist_image(source.name)
        return entry

    def snapshot(self):
        workflows = {entry["workflow"] for entry in self.entries}
        return {workflow: sorted((entry for entry in self.entries if entry["workflow"] == workflow),
                                key=lambda entry: (entry["created_at"], entry["name"]), reverse=True)
                for workflow in workflows}

    def original(self, name):
        return self.directory / name

    def thumbnail(self, name):
        return self.thumbnails / (Path(name).stem + ".jpg")
