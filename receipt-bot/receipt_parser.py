"""OCR текстийг (падан) мөр бүрээр нь [нэр, тоо, нэгжийн үнэ, нийт] болгон задлана."""
import re
from dataclasses import dataclass
from datetime import date

SKIP = re.compile(
    r"нийт|дүн|total|sum|нөат|ноат|тод|ттд|vat|cash|бэлэн|карт|card|change|"
    r"хариулт|сугалаа|lottery|баярлалаа|thank|ebarimt|и-баримт|дугаар|"
    r"qr|merchant|терминал|terminal|утас|tel|address|хаяг|нэгж үнэ|барааны нэр|"
    r"ддтд|дд[тт1]д|төлөх|бонус|номин|upoint|хувь|төрөл|төлбөр|хөнгөлөлт|discount|ү/н|№\s*нэр|бүтээгдэхүүн|бар\s*код|тоо\s*хэмжээ|хөн-|урамшуулал|данс|банк|захиалсан|хүргэх|худалдан\s*авагч",
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
    weak: bool = False  # тоо×үнэ=дүн батлагдаагүй


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


def _tokens(line: str):
    line = line.replace("|", " ").replace("₮", " ").replace("×", " ")
    line = re.sub(r"\s[xх*]\s", " ", line, flags=re.I)
    return line.split()


def _triple(nums):
    """Тоонуудаас qty*price≈total гэсэн гурвыг хайна."""
    n = len(nums)
    for i in range(n):
        q = nums[i]
        if not (0 < q <= 10000):
            continue
        for j in range(i + 1, n):
            p = nums[j]
            if p <= 0:
                continue
            for k in range(j + 1, n):
                t = nums[k]
                if t > 0 and abs(q * p - t) <= max(1.0, t * 0.0002):
                    return q, p, t
    return None


def grand_total(text: str):
    best = None
    for line in text.splitlines():
        if re.search(r"нийт\s*д|total", line, re.I) and not re.search(r"хөнгөлөлт", line, re.I):
            nums = [v for v in (_num(t) for t in _tokens(line)) if v]
            if nums:
                best = max(nums)
    return best


def _quality(name: str) -> float:
    """Нэрийн үсгийн эзлэх хувь (OCR-ийн хог тэмдэгт илрүүлэх)."""
    chars = [c for c in name if not c.isspace()]
    if not chars:
        return 0.0
    for w in name.split():  # нэг үгэнд кирилл+латин холилдвол OCR-ийн хог
        if re.search(r"[A-Za-z]", w) and re.search(r"[А-Яа-яӨөҮүЁё]", w):
            return 0.0
    return sum(c.isalpha() for c in chars) / len(chars)


def parse_items(text: str):
    items, pending = [], ""
    for raw in text.splitlines():
        line = raw.strip()
        if len(line) < 2 or SKIP.search(line):
            continue
        toks = [t for t in _tokens(line) if not re.fullmatch(r"\d{8,}", t)]  # бар код
        nums, words = [], []
        for t in toks:
            v = _num(t) if re.fullmatch(r"[\d][\d,.']*", t) else None
            (nums if v is not None else words).append(v if v is not None else t)
        # мөрийн дугаар (ө.х. "22 Olmeca ...") хасах
        if nums and words and toks and toks[0] == f"{nums[0]:.0f}" and nums[0] < 1000 and len(nums) >= 3:
            nums = nums[1:]
        for n, w in enumerate(words[:4]):  # барааны код (ND29, cn25) болон түүний өмнөх хог
            if len(words) > n + 1 and re.fullmatch(r"[A-Za-zА-Яа-яӨөҮү]{1,3}[\dOSЗ]{2,3}", w):
                words = words[n + 1:]
                break
        name = " ".join(words).strip(" .:-|_()—~")
        letters = re.search(r"[A-Za-zА-Яа-яӨөҮүЁё]{3}", name)
        if not nums:
            pending = line if re.search(r"[A-Za-zА-Яа-яӨөҮүЁё]{3}", line) else pending
            continue
        if not letters:
            name, pending = pending, ""
            if not name:
                continue
        else:
            pending = ""
        tr = _triple(nums) if len(nums) >= 3 else None
        if tr:
            if _quality(name) >= 0.6:
                items.append(Item(name, *tr))
            continue
        it = _build(name, _split(" ".join(toks))[1] or nums)
        # үнэ/тоо баталгаагүй мөр: нэр нь цэвэр, үнэ бодитой байх ёстой
        if it and it.total >= 500 and _quality(name) >= 0.85 and len(name) >= 4:
            it.weak = True
            items.append(it)
    return items


def all_numbers(text: str):
    """Нийт дүнгийн мөрүүд (нийт/төлөх/total) дээрх 1000-аас дээш тоонууд."""
    out = set()
    for line in text.splitlines():
        if not re.search(r"нийт|төлөх|total|sum", line, re.I) or re.search(r"хөнгөлөлт|урамшуулал", line, re.I):
            continue
        for t in line.replace("|", " ").split():
            if re.fullmatch(r"[\d][\d,.']*", t) and not re.fullmatch(r"\d{8,}", t):
                v = _num(t)
                if v and v >= 1000:
                    out.add(round(v))
    return out


def score(items, total, nums=()):
    """Нийт дүнтэй (эсвэл бичвэр доторх тоотой) таарвал өндөр оноо."""
    s = sum(i.total for i in items)
    ok = bool(items) and ((total is not None and abs(s - total) < 1) or round(s) in nums)
    return (ok, len(items))
