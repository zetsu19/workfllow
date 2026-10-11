"""Claude vision-аар падан унших (локал OCR нийт дүнтэй таараагүй үед л дуудна).
Haiku 5.5-аас эхэлж, таарахгүй бол дараагийн (илүү хүчтэй) загвар руу шилжинэ."""
import base64
import os
from typing import List, Optional

import anthropic
import cv2
import numpy as np
from pydantic import BaseModel

from receipt_parser import Item, find_date

MODELS = [m.strip() for m in os.environ.get("AI_MODELS", "claude-haiku-5-5,claude-sonnet-5-5").split(",") if m.strip()]
MAX_EDGE = 1568


class Line(BaseModel):
    name: str
    qty: float
    unit_price: float
    total: float


class Receipt(BaseModel):
    date: Optional[str]  # YYYY-MM-DD
    grand_total: Optional[float]
    items: List[Line]


SYSTEM = """You extract purchase lines from photos of Mongolian receipts and invoices (Cyrillic and Latin text, amounts in MNT).
Rules:
- One entry per purchased product row. Copy the product name exactly as printed (keep Cyrillic/Latin spelling and size such as 700ml); drop item codes (ND29, cn25), row numbers and barcodes.
- qty: quantity (may be decimal, e.g. 1.07). unit_price: price per unit as printed. total: line amount as printed. If qty*unit_price does not match total, trust the printed numbers and re-read the digits carefully.
- Ignore headers, VAT (НӨАТ), discounts, bonus/card/payment lines, totals, signatures and stamps. A second document visible at the edge of the photo is not part of the receipt.
- grand_total: the receipt's printed overall total (Нийт дүн), or null if not visible.
- date: receipt date as YYYY-MM-DD, or null.
Return every row even if the photo is skewed or partly shadowed."""


def available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY")) and bool(MODELS)


def _prep(data: bytes) -> str:
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    h, w = img.shape[:2]
    k = MAX_EDGE / max(h, w)
    if k < 1:
        img = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 88])
    return base64.standard_b64encode(buf.tobytes()).decode()


def _ask(client, model: str, b64: str, hints: List[str]) -> Receipt:
    text = "Extract the receipt."
    if hints:
        text += "\nProducts this business has bought before (use exactly this spelling when the row is the same product):\n- " + "\n- ".join(hints)
    resp = client.messages.parse(
        model=model,
        max_tokens=4096,
        system=SYSTEM,
        output_config={"effort": "low" if "haiku" in model else "medium"},
        output_format=Receipt,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
            {"type": "text", "text": text},
        ]}],
    )
    if resp.parsed_output is None:
        raise ValueError(f"no parsed output (stop_reason={resp.stop_reason})")
    return resp.parsed_output


def read_with_ai(data: bytes, hints: List[str] = (), client=None):
    """-> (items, grand_total, matched, date|None, model) | None"""
    client = client or anthropic.Anthropic()
    b64, best = _prep(data), None
    for model in MODELS:
        try:
            r = _ask(client, model, b64, list(hints))
        except Exception as e:  # сүлжээ/refusal/хязгаар: дараагийн загвар руу
            print(f"AI {model} failed: {e}")
            continue
        items = [Item(l.name.strip(), l.qty, l.unit_price, l.total) for l in r.items if l.total > 0 and l.name.strip()]
        s = sum(i.total for i in items)
        gt = r.grand_total
        matched = bool(items) and gt is not None and abs(s - gt) < 1
        when = find_date(r.date or "")
        res = (items, gt if gt else s, matched, when, model)
        if matched:
            return res
        if items and (best is None or abs(s - (gt or s)) < best[0]):
            best = (abs(s - (gt or s)), res)
    return best[1] if best else None
