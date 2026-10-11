"""OCR текстийг (падан) мөр бүрээр нь [нэр, тоо, нэгжийн үнэ, нийт] болгон задлана."""
import re
from dataclasses import dataclass
from datetime import date

SKIP = re.compile(
    r"нийт|дүн|total|sum|нөат|ноат|тод|ттд|vat|cash|бэлэн|карт|card|change|"
    r"хариулт|сугалаа|lottery|баярлалаа|thank|ebarimt|и-баримт|дугаар|"
    r"qr|merchant|терминал|terminal|утас|tel|address|хаяг|нэгж үнэ|барааны нэр|"
    r"төлбөр|хөнгөлөлт|discount|ү/н|№\s*нэр",
    re.I,
)
NUM = re.compile(r"^[\d][\d,.\s']*$")
DATE_RES = [
    (re.compile(r"(\d{4})[-./](\d{1,2})[-./](\d{1,2})"), "ymd"),
    (re.compile(r"(\d{1,2})[-./](\d{1,2})[-./](\d{4})"), "dmy"),
]


@dataclass
class Item:
    name: str
    qty: float
    price: float
    total: float


def _num(tok: str):
    t = tok.replace("₮", "").replace("'", "").replace(" ", "").strip()
    if not t:
        return None
    if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", t):
        t = t.replace(",", "")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", t):
        t = t.replace(".", "")
    elif "," in t:
        t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def find_date(text: str):
    for rx, order in DATE_RES:
        m = rx.search(text)
        if not m:
            continue
        a, b, c = map(int, m.groups())
        y, mo, d = (a, b, c) if order == "ymd" else (c, b, a)
        try:
            return date(y, mo, d)
        except ValueError:
            continue
    return None


def _split(line: str):
    """Мөрийн төгсгөлийн тоонуудыг (нэр, [тоонууд]) гэж салгана."""
    line = line.replace("₮", " ").replace("×", " x ")
    line = re.sub(r"\s[xх*]\s", " ", line, flags=re.I)  # '2 x 5,000'
    toks = line.split()
    nums = []
    while toks:
        v = _num(toks[-1])
        if v is None or not re.search(r"\d", toks[-1]):
            break
        nums.insert(0, v)
        toks.pop()
    return " ".join(toks).strip(" .:-|_"), nums


def _build(name, nums):
    if len(nums) >= 3:
        q, p, t = nums[-3:]
        if abs(q * p - t) <= max(1, t * 0.02):
            return Item(name, q, p, t)
        if len(nums) >= 2:  # name дотор тоо орсон байж болно
            p, t = nums[-2:]
            q = round(t / p) if p else 1
            return Item(name, q or 1, p, t)
    if len(nums) == 2:
        a, b = nums
        if a and b and b >= a and abs(round(b / a) - b / a) < 0.01 and a < 1000 and b / a > 1 and a == int(a) and a <= 200:
            return Item(name, a, round(b / a, 2), b)  # тоо, нийт
        return Item(name, 1, a, b) if abs(a - b) < 0.01 else Item(name, 1, b, b)
    if len(nums) == 1:
        return Item(name, 1, nums[0], nums[0])
    return None


def parse_items(text: str):
    items, pending = [], ""
    for raw in text.splitlines():
        line = raw.strip()
        if len(line) < 2 or SKIP.search(line):
            continue
        name, nums = _split(line)
        letters = re.search(r"[A-Za-zА-Яа-яӨөҮүЁё]{2}", name)
        if not nums:
            pending = line if letters else pending
            continue
        if not letters:  # зөвхөн тоотой мөр -> өмнөх нэрийн мөртэй нийлүүлнэ
            name, pending = pending, ""
        else:
            pending = ""
        if not name or max(nums) < 100 and len(nums) == 1 and nums[0] < 10:
            continue  # хэт жижиг/нэргүй мөр = дуу чимээ
        it = _build(name, nums)
        if it and it.total > 0:
            items.append(it)
    return items
