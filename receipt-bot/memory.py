"""Хэрэглэгчийн засвараас суралцах хөнгөн санах ой: нэрийн alias + өмнө худалдаж авсан барааны жагсаалт.
(Загварыг fine-tune хийхгүй; нэрийг локалд засаж, AI-д "мэдэх бараа" гэж зөвлөмж өгнө.)"""
import difflib
import json
import os


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


class Memory:
    def __init__(self, path: str):
        self.path = path
        try:
            self.d = json.load(open(path, encoding="utf-8"))
        except (OSError, ValueError):
            self.d = {}
        self.d.setdefault("aliases", {})
        self.d.setdefault("products", {})
        self.d.setdefault("last", {"start": 0, "count": 0})

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.d, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)

    def canon(self, name: str) -> str:
        key = _norm(name)
        if key in self.d["aliases"]:
            return self.d["aliases"][key]
        known = list(self.d["products"])
        m = difflib.get_close_matches(name, known, n=1, cutoff=0.9)
        return m[0] if m else name

    def apply(self, items):
        for it in items:
            it.name = self.canon(it.name)
        return items

    def remember(self, items):
        for it in items:
            self.d["products"][it.name] = self.d["products"].get(it.name, 0) + 1

    def learn(self, old: str, new: str):
        self.d["aliases"][_norm(old)] = new
        self.d["products"][new] = self.d["products"].get(new, 0) + 3  # засвар = илүү найдвартай

    def hints(self, n: int = 60):
        return [k for k, _ in sorted(self.d["products"].items(), key=lambda kv: -kv[1])[:n]]
