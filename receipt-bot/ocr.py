"""Зургийг цэвэрлээд Tesseract-аар хэд хэдэн хувилбараар уншина, нийт дүнтэй хамгийн сайн таарсныг сонгоно."""
import os
import subprocess
import tempfile

import cv2
import numpy as np

from receipt_parser import _quality, grand_total, parse_items, score

LANGS = os.environ.get("OCR_LANGS", "mon+eng")


def _variants(data: bytes):
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return []
    if img.shape[1] < 2000:
        k = 2000 / img.shape[1]
        img = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC)
    # сүүдэр арилгах: арын гэрлийг тооцоолоод хуваана
    bg = cv2.medianBlur(cv2.dilate(img, np.ones((15, 15), np.uint8)), 31)
    norm = cv2.normalize(cv2.divide(img, bg, scale=255), None, 0, 255, cv2.NORM_MINMAX)
    return [img, norm]


def _tess(img, psm: int, langs: str = None) -> str:
    with tempfile.NamedTemporaryFile(suffix=".png") as f:
        cv2.imwrite(f.name, img)
        r = subprocess.run(["tesseract", f.name, "stdout", "-l", langs or LANGS, "--psm", str(psm)],
                           capture_output=True, text=True, timeout=120)
    return r.stdout


def _refine_names(items, data):
    """Тоо/үнэ нь батлагдсан мөрүүдийн нэрийг латин (eng) уншилтаар сайжруулна."""
    texts = [_tess(v, p, "eng") for v, p in zip(_variants(data), (4, 6))]
    for it in items:
        best = it.name
        for t in texts:
            for line in t.splitlines():
                for c in parse_items(line):
                    if c.price == it.price and c.qty == it.qty:
                        if _quality(c.name) >= 0.8 and len(c.name) > len(best):
                            best = c.name
        it.name = best
    return items


def read_receipt(data: bytes):
    """-> (items, text, grand_total, matched)"""
    best = None
    for img in _variants(data):
        for psm in (6, 4):
            text = _tess(img, psm)
            items, total = parse_items(text), grand_total(text)
            sc = score(items, total)
            if best is None or sc > best[0]:
                best = (sc, items, text, total)
            if sc[0] and items:
                return _refine_names(items, data), text, total, True
    if best is None:
        return [], "", None, False
    _, items, text, total = best[0], best[1], best[2], best[3]
    matched = best[0][0]
    if total and not matched:  # нийт дүн таараагүй бол баталгаагүй мөрүүдийг хаяна
        items = [i for i in items if not i.weak]
    return _refine_names([i for i in items if not i.weak], data) + [i for i in items if i.weak], text, total, matched
