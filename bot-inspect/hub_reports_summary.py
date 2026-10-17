#!/usr/bin/env python3
"""hub_reports_summary.py - hub-ийн өдрийн тайлангууд (data/reports/*.json)-ыг НЭГТГЭЖ харуулна.

Зөвхөн унших (read-only). Зөвхөн Python stdlib. Нууц файл (auth.json, push_token)-д хүрэхгүй.
Тайлангийн бүтэц: {date, bots:[{id,label,q1,q2,q3,n,n_exec,n_skip,by_reason[],ideas[]}], method, headline,...}

Ажиллуулах (Oracle дээр):
    python3 hub_reports_summary.py                      # ~/hub/data/reports
    python3 hub_reports_summary.py --dir /зам/reports
"""
import argparse
import glob
import json
import os
from collections import Counter, defaultdict


def num(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def f(x, n=1):
    return "-" if x is None else f"{x:.{n}f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=os.path.expanduser("~/hub/data/reports"))
    a = ap.parse_args()
    files = sorted(glob.glob(os.path.join(a.dir, "*.json")))
    if not files:
        raise SystemExit(f"{a.dir} дотор *.json олдсонгүй")
    reports = []
    for p in files:
        try:
            reports.append(json.load(open(p, encoding="utf-8")))
        except Exception as e:
            print(f"(уншигдсангүй {os.path.basename(p)}: {e})")
    print(f"Тайлан: {len(reports)}   {reports[0].get('date')} -> {reports[-1].get('date')}")

    bots = defaultdict(lambda: Counter())
    reason = defaultdict(lambda: Counter())
    q3sum = 0.0
    reason_sum = 0.0
    ideas_all = []
    for r in reports:
        for b in r.get("bots", []):
            bid = b.get("label") or b.get("id")
            q3 = b.get("q3") or {}
            c = bots[bid]
            c["days"] += 1
            for k in ("n", "n_exec", "n_skip"):
                c[k] += b.get(k) or 0
            for k in ("correct", "wrong", "neutral", "unknown"):
                c[k] += q3.get(k) or 0
            for k in ("net_r", "saved_r", "missed_r"):
                c[k] += num(q3.get(k)) or 0
            q3sum += num(q3.get("net_r")) or 0
            for br in b.get("by_reason") or []:
                rc = reason[str(br.get("reason"))[:70]]
                for k in ("n", "correct", "wrong", "neutral", "unknown"):
                    rc[k] += br.get(k) or 0
                rc["net_r"] += num(br.get("net_r")) or 0
                reason_sum += num(br.get("net_r")) or 0
            for i in b.get("ideas") or []:
                ideas_all.append((r.get("date"), bid, i))

    print("\n== BOT-ООР (бүх хугацаа)   [saved−missed = net_r; сөрөг = шүүлт ашиг алдсан]")
    print(f"{'bot':28} {'setup':>6} {'орсон':>6} {'алгас':>6} {'зөв':>5} {'буруу':>6} {'ялгаагүй':>9} {'?':>4} {'saved':>7} {'missed':>8} {'net_r':>7}")
    for k, c in sorted(bots.items()):
        print(f"{str(k)[:28]:28} {c['n']:>6} {c['n_exec']:>6} {c['n_skip']:>6} {c['correct']:>5} {c['wrong']:>6} {c['neutral']:>9} {c['unknown']:>4} "
              f"{c['saved_r']:>7.1f} {c['missed_r']:>8.1f} {c['net_r']:>7.1f}")

    print("\n== АЛГАСАХ ШАЛТГААН (бүх bot, бүх өдөр)   net_r сөрөг = энэ шүүлт ашиг идсэн")
    print(f"{'шалтгаан':72} {'n':>5} {'зөв':>5} {'буруу':>6} {'ялг.':>5} {'?':>4} {'net_r':>7}")
    for k, c in sorted(reason.items(), key=lambda kv: -kv[1]["n"])[:20]:
        print(f"{k:72} {c['n']:>5} {c['correct']:>5} {c['wrong']:>6} {c['neutral']:>5} {c['unknown']:>4} {c['net_r']:>7.1f}")
    print(f"\nхяналт: Σ q3.net_r = {q3sum:.1f}   Σ by_reason.net_r = {reason_sum:.1f}   (ижил бол тэмдэглэгээ нэг)")

    n = len(ideas_all)
    ex = [x for x in ideas_all if x[2].get("executed")]
    with_r = [x for x in ideas_all if num(x[2].get("r")) is not None]
    print(f"\n== IDEA-УУД (setup бүр, bot-уудаар давхардсан): {n}   орсон: {len(ex)}   simulate-ийн R-тэй: {len(with_r)}")
    uniq = {(d, i.get("engine"), i.get("sym"), i.get("dir"), round(num(i.get("entry")) or 0, 1)) for d, _, i in ideas_all}
    print(f"   ойролцоо БИЕ ДААСАН setup (өдөр+engine+чиглэл+entry): {len(uniq)}")
    print("   verdict:", dict(Counter(str(i.get("verdict")) for _, _, i in ideas_all)))
    print("   engine :", dict(Counter(str(i.get("engine")) for _, _, i in ideas_all)))
    print("   sim    :", dict(Counter(str(i.get("sim"))[:50] for _, _, i in ideas_all).most_common(8)))
    rs = [num(i["r"]) for _, _, i in with_r]
    if rs:
        print(f"   simulate-ийн R: n={len(rs)}  нийлбэр={sum(rs):.1f}  дундаж={sum(rs) / len(rs):.2f}  win={100 * sum(1 for v in rs if v > 0) / len(rs):.0f}%")
        for flag in (True, False):
            v = [num(i["r"]) for _, _, i in with_r if bool(i.get("executed")) is flag]
            if v:
                print(f"     executed={flag}: n={len(v)}  нийлбэр={sum(v):.1f}  дундаж={sum(v) / len(v):.2f}")
    print("\n== ӨДРӨӨР: [огноо  partial  n_setup]")
    print("  " + "  ".join(f"{r.get('date')}:{sum((b.get('n') or 0) for b in r.get('bots', []))}" for r in reports))

    last = reports[-1]
    print("\n== method (сүүлийн тайлан; үнэлгээний арга):")
    print(str(last.get("method"))[:900])
    print("\n== headline (сүүлийн):", str(last.get("headline"))[:200])


if __name__ == "__main__":
    main()
