"""Зургийг цэвэрлээд Tesseract-аар хэд хэдэн хувилбараар уншина.
Хувилбар бүрээс гарсан мөрүүдийг нэгтгэж, нийт дүнтэй таарсныг сонгоно."""
import csv
import io
import os
import subprocess
import tempfile
from collections import Counter
from itertools import combinations

import cv2
import numpy as np

from receipt_parser import all_numbers, find_date, grand_total, parse_items

LANGS = os.environ.get("OCR_LANGS", "mon+eng")
MIN_WORD_CONF = 35  # үүнээс бага итгэлтэй үгийг (хог) хаяна


def _crop_paper(img):
    """Цаасны (хамгийн том тод) хэсгийг тайрч, хажуугийн хог бичвэрийг хасна."""
    h, w = img.shape
    blur = cv2.GaussianBlur(img, (0, 0), max(h, w) / 150)
    _, th = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    k = max(h, w) // 25
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
    cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return img
    x, y, bw, bh = cv2.boundingRect(max(cnts, key=cv2.contourArea))
    if bw * bh < 0.2 * w * h or bw * bh > 0.92 * w * h:
        return img
    m = 10
    return img[max(0, y - m):y + bh + m, max(0, x - m):x + bw + m]


def _crop_text(img, norm):
    """Бичвэрийн нягт хэсгийн (баганы проекцоор) хүрээг тайрна."""
    h, w = norm.shape
    m = (norm < 170).astype(np.uint8)
    cols = m.sum(axis=0) > 0.04 * h
    rows = m.sum(axis=1) > 0.01 * w
    if cols.sum() < 0.15 * w or rows.sum() < 0.15 * h:
        return None
    xs, ys = np.where(cols)[0], np.where(rows)[0]
    x0, x1, y0, y1 = xs[0], xs[-1], ys[0], ys[-1]
    if (x1 - x0) > 0.97 * w and (y1 - y0) > 0.97 * h:
        return None
    mg = 12
    return (max(0, x0 - mg), min(w, x1 + mg), max(0, y0 - mg), min(h, y1 + mg))


def _variants(data: bytes):
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return []
    img = _crop_paper(img)
    if img.shape[1] < 2000:
        k = 2000 / img.shape[1]
        img = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC)
    # сүүдэр арилгах: арын гэрлийг тооцоолоод хуваана
    bg = cv2.medianBlur(cv2.dilate(img, np.ones((15, 15), np.uint8)), 31)
    norm = cv2.normalize(cv2.divide(img, bg, scale=255), None, 0, 255, cv2.NORM_MINMAX)
    out = [img, norm]
    box = _crop_text(img, norm)
    if box:
        x0, x1, y0, y1 = box
        tight = norm[y0:y1, x0:x1]
        if tight.shape[1] < 2200:
            k = 2200 / tight.shape[1]
            tight = cv2.resize(tight, None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC)
        out.append(tight)
    return out


def _tess_lines(img, psm: int, langs: str):
    """-> [(мөрийн бичвэр, дундаж итгэл)]; итгэл багатай үсгэн үгийг хаясан."""
    with tempfile.NamedTemporaryFile(suffix=".png") as f:
        cv2.imwrite(f.name, img)
        r = subprocess.run(["tesseract", f.name, "stdout", "-l", langs, "--psm", str(psm), "tsv"],
                           capture_output=True, text=True, timeout=120)
    rows = csv.reader(io.StringIO(r.stdout), delimiter="\t", quoting=csv.QUOTE_NONE)
    lines = {}
    for row in rows:
        if len(row) < 12 or row[0] != "5":
            continue
        text = row[11].strip()
        if not text:
            continue
        key = tuple(row[2:5])
        lines.setdefault(key, []).append((int(row[6]), text, float(row[10])))
    out = []
    for words in lines.values():
        words.sort()
        keep, confs = [], []
        for _, t, c in words:
            isnum = any(ch.isdigit() for ch in t)
            if not isnum and c < MIN_WORD_CONF:
                continue
            keep.append(t)
            if not isnum:
                confs.append(c)
        if keep:
            out.append((" ".join(keep), sum(confs) / len(confs) if confs else 0.0))
    return out


def _key(it):
    return (it.qty, it.price, it.total)


def _pass_items(lines):
    """Нэг уншилтын мөрүүдээс {key: (нэр, итгэл)} ба Counter."""
    cnt, best = Counter(), {}
    seen = set()
    for text, conf in lines:  # мөр бүрийг тусад нь (итгэлтэй)
        for it in parse_items(text):
            cnt[_key(it)] += 1
            seen.add(id(it))
            if _key(it) not in best or conf > best[_key(it)][1]:
                best[_key(it)] = (it, conf)
    whole = parse_items("\n".join(t for t, _ in lines))  # нэр/тоо тусдаа мөрөнд байх тохиолдол
    wc = Counter(_key(i) for i in whole)
    for it in whole:
        if _key(it) not in best:
            best[_key(it)] = (it, 0.0)
    for k, n in wc.items():
        cnt[k] = max(cnt[k], n)
    return cnt, best


def read_receipt(data: bytes):
    """-> (items, grand_total, matched, date|None)"""
    variants = _variants(data)
    if not variants:
        return [], None, False, None
    passes = []  # (counter, best, text)
    for vi, img in enumerate(variants):
        for psm, langs in ((6, LANGS), (4, LANGS), (4, "eng")):
            lines = _tess_lines(img, psm, langs)
            cnt, best = _pass_items(lines)
            passes.append((cnt, best, "\n".join(t for t, _ in lines)))
    when = next((d for d in (find_date(t) for _, _, t in passes) if d), None)
    nums, totals = set(), []
    for _, _, text in passes:
        nums |= all_numbers(text)
        g = grand_total(text)
        if g:
            totals.append(g)
    nums |= {round(t) for t in totals}

    # хувилбар бүрийн үр дүн + бүгдийн нэгдэл
    union = Counter()
    for cnt, _, _ in passes:
        for k, n in cnt.items():
            union[k] = max(union[k], n)
    names = {}  # key -> [(Item, conf)] нэрээр нь ялгагдсан, итгэлээрээ эрэмбэлэгдсэн
    for _, best, _ in passes:
        for k, (it, conf) in best.items():
            lst = names.setdefault(k, [])
            for n, (old, oc) in enumerate(lst):
                if old.name == it.name:
                    lst[n] = (old, max(oc, conf))
                    break
            else:
                lst.append((it, conf))
    for lst in names.values():
        lst.sort(key=lambda p: (-p[1], -len(p[0].name)))

    def build(cnt):
        items, confs = [], []
        for k, n in cnt.items():
            for i in range(n):
                it, c = names[k][min(i, len(names[k]) - 1)]
                items.append(type(it)(it.name, it.qty, it.price, it.total, it.weak))
                confs.append(c)
        return items, confs

    built, confs = build(union)
    strong = sum(not i.weak for i in built)
    # "тоо×үнэ=дүн" батлагдсан мөр 3+ байвал баталгаагүй (weak) мөр бүгд OCR-ийн хог
    keep = [n for n, i in enumerate(built) if not (i.weak and (totals or strong >= 3)) and i.total < 2e7]
    items, conf = [built[n] for n in keep], [confs[n] for n in keep]

    def matches(s):
        s = round(s)
        return s in nums or any(len(str(n)) >= 5 and s != n and str(s).endswith(str(n)) for n in nums)

    if items and matches(sum(i.total for i in items)):
        return items, sum(i.total for i in items), True, when
    # хог мөр орсон байж болно: 1-2 мөрийг хасаад нийт дүнтэй таарах эсэхийг шалгана
    best = None
    for r in (1, 2):
        for idx in combinations(range(len(items)), r):
            rest = sum(i.total for j, i in enumerate(items) if j not in idx)
            if matches(rest):
                c = sum(conf[j] for j in idx)
                if best is None or c < best[0]:
                    best = (c, idx)
        if best:
            break
    if best:
        items = [i for j, i in enumerate(items) if j not in best[1]]
        return items, sum(i.total for i in items), True, when
    return items, (max(totals) if totals else sum(i.total for i in items)), False, when
