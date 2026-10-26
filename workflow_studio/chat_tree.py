"""Conversation branches on temporary disk for the current kernel run."""
import atexit
import base64
import io
import json
from pathlib import Path
import secrets
import sqlite3
import tempfile
import threading
from PIL import Image, ImageOps
from content_store import enabled


SESSION_DIRECTORY = tempfile.TemporaryDirectory(prefix="workflow-studio-chats-")


class ChatTree:
    def __init__(self):
        self.path = Path(SESSION_DIRECTORY.name) / f"{secrets.token_hex(8)}.sqlite3"
        self.db = sqlite3.connect(':memory:' if enabled() else self.path, check_same_thread=False)
        self.images = {}
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.db.executescript("""
            CREATE TABLE nodes (
                id TEXT PRIMARY KEY, parent TEXT, role TEXT, content TEXT,
                reasoning TEXT, status TEXT, attachments TEXT DEFAULT '[]'
            );
            CREATE INDEX node_parent ON nodes(parent);
            CREATE TABLE selected (parent TEXT PRIMARY KEY, child TEXT);
        """)
        self.active = None
        self._response = None
        atexit.register(self.close)

    def close(self):
        self._response = None
        self.db.close()
        self.images.clear()

    def _node(self, node_id):
        if self._response and self._response["id"] == node_id:
            return self._response.copy()
        node = dict(self.db.execute("SELECT * FROM nodes WHERE id = ?", (node_id,)).fetchone())
        node["attachments"] = json.loads(node["attachments"])
        return node

    def store_images(self, images):
        directory = self.path.with_suffix("")
        directory.mkdir(exist_ok=True)
        attachments = []
        for image in images:
            data = base64.b64decode(image["url"].split(",", 1)[1])
            source = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
            filename = secrets.token_hex(8) + ".png"
            if enabled():
                original = io.BytesIO()
                source.save(original, 'PNG')
                self.images[filename] = original.getvalue()
            else:
                source.save(directory / filename)
            source.thumbnail((512, 512))
            preview = io.BytesIO()
            source.save(preview, "JPEG", quality=85)
            attachments.append({"name": image["name"], "file": filename,
                                "preview": "data:image/jpeg;base64," + base64.b64encode(preview.getvalue()).decode()})
        return attachments

    def image_bytes(self, name):
        return self.images[name] if enabled() else (self.path.with_suffix('') / name).read_bytes()

    def _flush(self):
        if self._response:
            node = self._response
            self.db.execute("UPDATE nodes SET content = ?, reasoning = ?, status = ? WHERE id = ?",
                            (node["content"], node["reasoning"], node["status"], node["id"]))
            self._response = None
        self.db.commit()

    def _path_nodes(self):
        path = []
        node_id = self.active
        while node_id:
            node = self._node(node_id)
            path.append(node)
            node_id = node["parent"]
        return path[::-1]

    def snapshot(self):
        with self.lock:
            path = self._path_nodes()
            roots = [dict(row) for row in self.db.execute(
                "SELECT id, CASE WHEN content = '' THEN '图片提问' ELSE substr(content, 1, 45) END AS label "
                "FROM nodes WHERE parent IS NULL ORDER BY rowid")]
            siblings = {node["parent"] or "": [row[0] for row in self.db.execute(
                "SELECT id FROM nodes WHERE parent IS ? ORDER BY rowid", (node["parent"],))] for node in path}
            return {"nodes": {node["id"]: node for node in path}, "active": self.active,
                    "roots": roots, "siblings": siblings}

    def _append(self, role, content, parent, attachments=None):
        node = {"id": secrets.token_hex(5), "parent": parent, "role": role, "content": content,
                "reasoning": "", "status": "done" if role == "user" else "pending", "attachments": attachments or []}
        self.db.execute("INSERT INTO nodes VALUES (:id, :parent, :role, :content, :reasoning, :status, :attachments)",
                        {**node, "attachments": json.dumps(node["attachments"])})
        self.db.execute("INSERT OR REPLACE INTO selected VALUES (?, ?)", (parent or "", node["id"]))
        self.active = node["id"]
        return node

    def send(self, text, images=None):
        with self.lock:
            self._flush()
            user = self._append("user", text, self.active, self.store_images(images or []))
            answer = self._append("assistant", "", user["id"])
            self.db.commit()
            return answer

    def edit(self, node_id, text):
        with self.lock:
            self._flush()
            user = self._node(node_id)
            self._select(node_id)
            edited = self._append("user", text, user["parent"], user["attachments"])
            answer = self._append("assistant", "", edited["id"])
            self.db.commit()
            return answer

    def retry(self, node_id):
        with self.lock:
            self._flush()
            node = self._node(node_id)
            user_id = node["id"] if node["role"] == "user" else node["parent"]
            self._select(user_id)
            answer = self._append("assistant", "", user_id)
            self.db.commit()
            return answer

    def _select(self, node_id):
        node = self._node(node_id)
        while node:
            self.db.execute("INSERT OR REPLACE INTO selected VALUES (?, ?)", (node["parent"] or "", node["id"]))
            node = self._node(node["parent"]) if node["parent"] else None
        while True:
            child = self.db.execute("SELECT child FROM selected WHERE parent = ?", (node_id,)).fetchone()
            if child is None:
                break
            node_id = child[0]
        self.active = node_id

    def select(self, node_id):
        with self.lock:
            self._flush()
            self._select(node_id)
            self.db.commit()

    def messages(self):
        with self.lock:
            messages = []
            for node in self._path_nodes():
                if node["role"] != "user" and not node["content"]:
                    continue
                content = node["content"]
                if node["attachments"]:
                    content = [{"type": "image_url", "image_url": {"url": "data:image/png;base64," +
                                base64.b64encode(self.image_bytes(image["file"])).decode()}}
                               for image in node["attachments"]] + [{"type": "text", "text": content}]
                messages.append({"role": node["role"], "content": content})
            return messages

    def response(self, content, reasoning=None):
        with self.lock:
            if self._response is None:
                self._response = self._node(self.active)
            self._response["content"] = content
            if reasoning is not None:
                self._response["reasoning"] = reasoning
            return self._response.copy()

    def finish(self, status):
        with self.lock:
            self._flush()
            self.db.execute("UPDATE nodes SET status = ? WHERE id = ?", (status, self.active))
            self.db.commit()

    def new(self):
        with self.lock:
            self._flush()
            self.active = None

    def export(self):
        with self.lock:
            self._flush()
            data = {"nodes": {row["id"]: dict(row) for row in self.db.execute("SELECT * FROM nodes ORDER BY rowid")},
                    "active": self.active, "selected": dict(self.db.execute("SELECT parent, child FROM selected"))}
            for node in data["nodes"].values():
                node["attachments"] = json.loads(node["attachments"])
                for image in node["attachments"]:
                    image["url"] = "data:image/png;base64," + base64.b64encode(
                        self.image_bytes(image["file"])).decode()
            return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")

    def import_snapshot(self, data):
        with self.lock:
            nodes = [{**node, "attachments": json.dumps(self.store_images(node.get("attachments", [])))}
                     for node in data["nodes"].values()]
            self.db.executemany("INSERT INTO nodes VALUES (:id, :parent, :role, :content, :reasoning, :status, :attachments)", nodes)
            self.db.executemany("INSERT INTO selected VALUES (?, ?)", data["selected"].items())
            self.active = data["active"]
            self.db.commit()
