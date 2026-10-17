#!/usr/bin/env python3
"""analyze_trades.py - /opt/bots/trades/*.json доторх арилжааны түүхийг УНШИЖ статистик тайлан гаргана.

Зөвхөн унших (read-only). Бичихгүй, bot/контейнерт хүрэхгүй. Зөвхөн Python stdlib.
Тикет, magic, comment гэх мэт таних мэдээллийг хэвлэхгүй.

Ажиллуулах:
    python3 analyze_trades.py                         # бүх файл
    python3 analyze_trades.py --dir /opt/bots/trades  # хавтас заах
    python3 analyze_trades.py --since-days 14         # сүүлийн 14 хоногийн хаасан арилжаа
    python3 analyze_trades.py --skip-logs bot-d --hours 72   # bot-d-ийн CONFIRM-SKIP шалтгаан
"""
import argparse
import glob
import json
import os
import re
import statistics as st
import subprocess
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone

RULE_MIN_RR = 2.0        # trade_ledger.py RULES
RULE_MAX_RISK_PCT = 1.5
RULE_BEYOND_SL_R = -1.05
CLUSTER_N, CLUSTER_MIN = 3, 60


def load(path):
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    t = d.get("trades", {})
    items = list(t.values()) if isinstance(t, dict) else list(t)
    return d.get("updated"), [x for x in items if isinstance(x, dict)]


def num(x, default=None):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else default


def fmt(x, n=2):
    return "-" if x is None else f"{x:.{n}f}"


def pct(a, b):
    return "-" if not b else f"{100 * a / b:.0f}%"


def mean(v):
    return st.mean(v) if v else None


def median(v):
    return st.median(v) if v else None


def stats_block(name, rs):
    """rs: R-үр дүнгийн жагсаалт (хаалтын дарааллаар)."""
    if not rs:
        return f"  {name}: арилжаа байхгүй"
    wins = [r for r in rs if r > 0]
    loss = [r for r in rs if r < 0]
    gp, gl = sum(wins), -sum(loss)
    pf = (gp / gl) if gl else None
    cum, peak, mdd = 0.0, 0.0, 0.0
    for r in rs:
        cum += r
        peak = max(peak, cum)
        mdd = max(mdd, peak - cum)
    return (f"  {name}: n={len(rs)}  win={pct(len(wins), len(rs))}  "
            f"нийт R={fmt(sum(rs))}  дундаж R={fmt(mean(rs), 3)}  "
            f"PF={fmt(pf)}  дундаж win={fmt(mean(wins))}R  дундаж loss={fmt(mean(loss))}R  "
            f"max DD={fmt(mdd)}R")


def analyze_file(path, since_ts):
    updated, items = load(path)
    name = os.path.basename(path)
    out = [f"\n{'=' * 70}\n{name}   нийт бичлэг: {len(items)}"]
    if updated:
        out.append(f"  сүүлд шинэчлэгдсэн: {datetime.fromtimestamp(updated, timezone.utc):%Y-%m-%d %H:%M} UTC")
    status = Counter(str(x.get("status")) for x in items)
    out.append(f"  status: {dict(status)}")

    closed = [x for x in items if num(x.get("closed_ts")) and num(x.get("r")) is not None]
    if since_ts:
        closed = [x for x in closed if x["closed_ts"] >= since_ts]
    closed.sort(key=lambda x: x["closed_ts"])
    open_n = len(items) - len([x for x in items if num(x.get("closed_ts"))])
    out.append(f"  хаагдсан (шинжилгээнд): {len(closed)}   нээлттэй/хаагдаагүй: {open_n}")
    if not closed:
        return "\n".join(out), closed

    rs = [x["r"] for x in closed]
    out.append(stats_block("БҮГД", rs))
    pnl = [x["pnl"] for x in closed if num(x.get("pnl")) is not None]
    if pnl:
        out.append(f"  PnL нийт={fmt(sum(pnl))}$  дундаж={fmt(mean(pnl))}$  "
                   f"хамгийн сайн={fmt(max(pnl))}$  хамгийн муу={fmt(min(pnl))}$")
    first, last = closed[0]["closed_ts"], closed[-1]["closed_ts"]
    out.append(f"  хугацаа: {datetime.fromtimestamp(first, timezone.utc):%Y-%m-%d} -> "
               f"{datetime.fromtimestamp(last, timezone.utc):%Y-%m-%d}")

    # чиглэл, symbol
    for label, key in (("ЧИГЛЭЛЭЭР", "dir"), ("SYMBOL-ООР", "symbol")):
        g = defaultdict(list)
        for x in closed:
            g[str(x.get(key))].append(x["r"])
        out.append(f"  -- {label}")
        for k, v in sorted(g.items()):
            out.append(stats_block(k, v))

    # Гаралтын үр ашиг: авсан R / боломжит MFE
    cap = [x["r"] / x["mfe_r"] for x in closed
           if num(x.get("mfe_r")) and x["mfe_r"] > 0.2 and x["r"] > 0]
    gave = [x for x in closed if num(x.get("mfe_r"), 0) >= 1.0 and x["r"] <= 0]
    gave_be = [x for x in closed if num(x.get("mfe_r"), 0) >= 1.0 and -0.1 <= x["r"] <= 0.1]
    out.append("  -- ГАРАЛТЫН ҮР АШИГ (mfe_r / mae_r)")
    out.append(f"  ашигтай арилжаанд авсан R / боломжит MFE: медиан={fmt(median(cap), 2)}  (n={len(cap)}; 1.0=хамгийн оргилд гарсан)")
    out.append(f"  +1R хүрээд дараа нь алдсан/0 болсон: {len(gave)} ({pct(len(gave), len(closed))})"
               f"   үүнээс ~breakeven: {len(gave_be)}")
    win_mae = [abs(x["mae_r"]) for x in closed if x["r"] > 0 and num(x.get("mae_r")) is not None]
    los_mfe = [x["mfe_r"] for x in closed if x["r"] < 0 and num(x.get("mfe_r")) is not None]
    out.append(f"  ашигтай арилжааны дундаж эсрэг явалт |mae_r|={fmt(mean(win_mae))}R  "
               f"(1.0 орчим бол SL-д дөхөж байгаад ашигтай болсон)")
    out.append(f"  алдагдалтай арилжааны дундаж боломжит ашиг mfe_r={fmt(mean(los_mfe))}R")

    # SL зөөлт
    out.append("  -- SL ЗӨӨЛТ (moved_sl)")
    for flag in (True, False):
        v = [x["r"] for x in closed if x.get("moved_sl") is flag]
        out.append(stats_block(f"moved_sl={flag}", v))

    # Төлөвлөсөн vs бодит
    plan = [x for x in closed if num(x.get("rr_plan"))]
    if plan:
        out.append("  -- ТӨЛӨВЛӨГӨӨ vs БОДИТ")
        out.append(f"  rr_plan дундаж={fmt(mean([x['rr_plan'] for x in plan]))}   "
                   f"бодит дундаж R={fmt(mean([x['r'] for x in plan]), 3)}")
        low_rr = [x for x in plan if x["rr_plan"] < RULE_MIN_RR]
        out.append(f"  rr_plan < {RULE_MIN_RR} (дүрэм зөрчсөн): {len(low_rr)} ({pct(len(low_rr), len(plan))})")
    rp = [x["risk_pct"] for x in closed if num(x.get("risk_pct")) is not None]
    if rp:
        over = [x for x in closed if num(x.get("risk_pct"), 0) > RULE_MAX_RISK_PCT]
        out.append(f"  risk_pct дундаж={fmt(mean(rp))}%  хамгийн их={fmt(max(rp))}%  "
                   f"> {RULE_MAX_RISK_PCT}% : {len(over)} арилжаа")
    slip = [x for x in closed if x["r"] < RULE_BEYOND_SL_R]
    out.append(f"  SL-ээс цааш алдсан (r < {RULE_BEYOND_SL_R}, slippage/gap): {len(slip)}"
               + (f"   дундаж={fmt(mean([x['r'] for x in slip]))}R" if slip else ""))

    # Хугацаа
    dm = [x["dur_min"] for x in closed if num(x.get("dur_min")) is not None]
    if dm:
        out.append(f"  байсан хугацаа (мин): медиан={fmt(median(dm), 0)}  дундаж={fmt(mean(dm), 0)}  max={fmt(max(dm), 0)}")

    # Цагаар (нээсэн цаг, UTC)
    byh = defaultdict(list)
    for x in closed:
        if num(x.get("opened_ts")):
            byh[datetime.fromtimestamp(x["opened_ts"], timezone.utc).hour].append(x["r"])
    if byh:
        out.append("  -- НЭЭСЭН ЦАГААР (UTC)  [цаг: n, нийт R]")
        out.append("  " + "  ".join(f"{h:02d}:{len(v)},{sum(v):+.1f}" for h, v in sorted(byh.items())))

    # Давхар орох (cluster)
    opened = sorted((x for x in closed if num(x.get("opened_ts"))), key=lambda x: x["opened_ts"])
    grp = defaultdict(list)
    for x in opened:
        grp[(x.get("symbol"), x.get("dir"))].append(x)
    clustered = set()
    for lst in grp.values():
        for i, x in enumerate(lst):
            w = [y for y in lst if 0 <= y["opened_ts"] - x["opened_ts"] <= CLUSTER_MIN * 60]
            if len(w) >= CLUSTER_N:
                clustered.update(id(y) for y in w)
    cl = [x["r"] for x in closed if id(x) in clustered]
    ncl = [x["r"] for x in closed if id(x) not in clustered]
    out.append(f"  -- CLUSTER ({CLUSTER_N}+ ижил чиглэл {CLUSTER_MIN} мин дотор)")
    out.append(stats_block("cluster-д орсон", cl))
    out.append(stats_block("бусад", ncl))

    # flags
    fg = defaultdict(list)
    for x in closed:
        fl = x.get("flags")
        for f in (fl if isinstance(fl, list) else []):
            fg[str(f)].append(x["r"])
    if fg:
        out.append("  -- FLAGS  [flag: n, дундаж R]")
        for f, v in sorted(fg.items(), key=lambda kv: -len(kv[1]))[:12]:
            out.append(f"  {f[:40]:40} n={len(v):3}  avgR={fmt(mean(v), 2)}")

    out.extend(ml_and_cost_section(closed))
    return "\n".join(out), closed


def truthy(v):
    """would_allow хэлбэр (bool, 0/1, 'yes'/'allow' ...) -> True/False/None."""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        t = v.strip().lower()
        if t in ("true", "yes", "y", "1", "allow", "allowed", "ok", "pass"):
            return True
        if t in ("false", "no", "n", "0", "block", "blocked", "deny", "skip", ""):
            return False
    return None


def ml_and_cost_section(closed):
    out = []
    wins = [x["r"] for x in closed if x["r"] > 0]
    loss = [-x["r"] for x in closed if x["r"] < 0]
    if wins and loss:
        be = mean(loss) / (mean(wins) + mean(loss))
        act = len(wins) / len(closed)
        out.append("  -- ЦЭВЭР ТЭНЦЭЛ (бодит дундаж ашиг/алдагдлаар)")
        out.append(f"  ашиг-алдагдалгүй болоход хэрэгтэй win rate={100 * be:.0f}%   бодит win rate={100 * act:.0f}%")

    rn = [(x["r"], x["ml"]["r_net"]) for x in closed
          if isinstance(x.get("ml"), dict) and num(x["ml"].get("r_net")) is not None]
    if rn:
        out.append("  -- r vs r_net (r_net-ийн тодорхойлолт кодоос баталгаажаагүй)")
        out.append(f"  r дундаж={fmt(mean([a for a, _ in rn]), 3)}R   r_net дундаж={fmt(mean([b for _, b in rn]), 3)}R   "
                   f"зөрүү (r - r_net) дундаж={fmt(mean([a - b for a, b in rn]), 3)}R")

    mlx = [x for x in closed if isinstance(x.get("ml"), dict)]
    if not mlx:
        return out
    out.append("  -- ML ШҮҮЛТҮҮР (ml.would_allow, ml.prob)")
    out.append(f"  ML mode: {dict(Counter(str(x['ml'].get('mode')) for x in mlx))}   model: {dict(Counter(str(x['ml'].get('model')) for x in mlx))}")
    out.append(f"  would_allow түүхий утгууд: {dict(Counter(repr(x['ml'].get('would_allow')) for x in mlx))}")
    out.append(f"  prob төрөл: {dict(Counter(type(x['ml'].get('prob')).__name__ for x in mlx))}   "
               f"threshold жишээ: {sorted({repr(x['ml'].get('threshold')) for x in mlx})[:4]}")
    for label, want in (("would_allow=ТИЙМ", True), ("would_allow=ҮГҮЙ", False)):
        v = [x["r"] for x in mlx if truthy(x["ml"].get("would_allow")) is want]
        out.append(stats_block(label, v))
    unk = [x["r"] for x in mlx if truthy(x["ml"].get("would_allow")) is None]
    if unk:
        out.append(stats_block("would_allow=тодорхойгүй", unk))

    def pnum(x):
        v = x["ml"].get("prob")
        if isinstance(v, str):
            try:
                return float(v)
            except ValueError:
                return None
        return num(v)
    pr = sorted((x for x in mlx if pnum(x) is not None), key=pnum)
    if len(pr) >= 6:
        k = len(pr) // 3
        for label, part in (("prob доод 1/3", pr[:k]), ("prob дунд 1/3", pr[k:2 * k]), ("prob дээд 1/3", pr[2 * k:])):
            ps = [pnum(x) for x in part]
            out.append(stats_block(f"{label} [{min(ps):.2f}..{max(ps):.2f}]", [x["r"] for x in part]))
    rs = defaultdict(list)
    for x in mlx:
        rs[str(x["ml"].get("reason"))[:36]].append(x["r"])
    out.append("  ML reason  [n, дундаж R]")
    for k, v in sorted(rs.items(), key=lambda kv: -len(kv[1]))[:8]:
        out.append(f"  {k:36} n={len(v):3}  avgR={fmt(mean(v), 2)}")
    return out


def skip_reasons(container, hours):
    try:
        raw = subprocess.run(["docker", "logs", "--since", f"{hours}h", container],
                             capture_output=True, text=True, timeout=60)
    except Exception as e:  # docker байхгүй гэх мэт
        return f"\n(docker logs уншиж чадсангүй: {e})"
    text = raw.stdout + raw.stderr
    reasons = Counter(re.findall(r"CONFIRM-SKIP\].*?reason=([a-z_]+)", text))
    setups = len(re.findall(r"GOLD H4 CRT (?:LONG|SHORT)", text))
    out = [f"\n{'=' * 70}\n{container}: сүүлийн {hours}ц-ийн CONFIRM-SKIP шалтгаанууд (setup мөр: {setups})"]
    if not reasons:
        out.append("  олдсонгүй (зах зээл хаалттай эсвэл kill zone-ийн гадна байж болно)")
    for k, n in reasons.most_common():
        out.append(f"  {k:20} {n}")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="/opt/bots/trades")
    ap.add_argument("--since-days", type=float, default=0)
    ap.add_argument("--skip-logs", default="", help="контейнерийн нэр, жишээ bot-d")
    ap.add_argument("--hours", type=int, default=72)
    a = ap.parse_args()

    since = time.time() - a.since_days * 86400 if a.since_days else 0
    files = sorted(glob.glob(os.path.join(a.dir, "*.json")))
    if not files:
        raise SystemExit(f"{a.dir} дотор *.json олдсонгүй")
    print(f"Тайлан: {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC   хавтас: {a.dir}"
          + (f"   сүүлийн {a.since_days:g} хоног" if since else ""))
    allc = []
    for f in files:
        try:
            text, closed = analyze_file(f, since)
        except Exception as e:
            text, closed = f"\n{os.path.basename(f)}: уншиж чадсангүй ({e})", []
        print(text)
        allc += closed
    if len(files) > 1 and allc:
        print(f"\n{'=' * 70}\nНИЙТ (бүх bot)")
        print(stats_block("бүгд", [x["r"] for x in sorted(allc, key=lambda x: x["closed_ts"])]))
    if a.skip_logs:
        print(skip_reasons(a.skip_logs, a.hours))


if __name__ == "__main__":
    main()
