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
    ap.add_argument("--family", default="", help="engine нэрэнд агуулагдах үг (жишээ SMC, V6, TDV, CRT): дэлгэрэнгүй задаргааг зөвхөн тэдэнд хязгаарлана")
    ap.add_argument("--csv", default="", help="бүх idea-г CSV болгон хадгалах (дараа нь гараар шинжлэхэд)")
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
    if a.csv:
        import csv
        with open(a.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["date", "bot", "engine", "sym", "dir", "t", "t_last", "entry", "sl", "tp1", "scans", "executed", "reason", "sim", "r", "mfe_r", "mae_r", "verdict"])
            for d, b, i in ideas_all:
                w.writerow([d, b, i.get("engine"), i.get("sym"), i.get("dir"), i.get("t"), i.get("t_last"), i.get("entry"), i.get("sl"), i.get("tp1"),
                            i.get("scans"), int(bool(i.get("executed"))), str(i.get("reason"))[:80], i.get("sim"), i.get("r"), i.get("mfe_r"), i.get("mae_r"), i.get("verdict")])
        print(f"\nCSV хадгаллаа: {a.csv}  ({len(ideas_all)} мөр)")
    if a.family:
        fam = a.family.lower()
        with_r = [x for x in with_r if fam in str(x[2].get("engine")).lower()]
        print(f"\n##### ДЭЛГЭРЭНГҮЙ ЗАДАРГАА: engine ~ '{a.family}'  (R-тэй idea: {len(with_r)}) #####")
    # ---- дэлгэрэнгүй: R-тэй idea-уудыг шинж чанараар нь задлах ----
    def line(name, vals):
        if not vals:
            return f"  {name[:46]:46} n=0"
        w = sum(1 for v in vals if v > 0)
        return f"  {name[:46]:46} n={len(vals):4}  Σ={sum(vals):7.1f}R  дундаж={sum(vals) / len(vals):6.2f}R  win={100 * w / len(vals):3.0f}%"

    def group(title, keyfn, minn=1):
        g = defaultdict(list)
        for d, b, i in with_r:
            k = keyfn(d, b, i)
            if k is not None:
                g[k].append(num(i["r"]))
        print(f"\n== {title} (зөвхөн R-тэй idea)")
        for k, v in sorted(g.items(), key=lambda kv: -len(kv[1])):
            if len(v) >= minn:
                print(line(str(k), v))

    group("ENGINE-ЭЭР", lambda d, b, i: str(i.get("engine")), 5)
    group("ENGINE x ОРСОН/АЛГАССАН", lambda d, b, i: f"{i.get('engine')} | {'орсон' if i.get('executed') else 'алгассан'}", 8)
    group("ЧИГЛЭЛЭЭР", lambda d, b, i: str(i.get("dir")), 1)
    group("ENGINE-FAMILY x ЧИГЛЭЛ", lambda d, b, i: f"{str(i.get('engine')).split()[0]} | {i.get('dir')}", 5)
    group("SIM АНГИЛАЛААР (hub-ийн үр дүн)", lambda d, b, i: str(i.get("sim")), 1)
    group("АЛГАСАХ ШАЛТГААНААР: дундаж R (алгассан idea; ихэвчлэн сөрөг = алгасах нь зөв)",
          lambda d, b, i: None if i.get("executed") else str(i.get("reason"))[:46], 15)
    group("АЛГАСАХ ШАЛТГААН x ENGINE-FAMILY (алгассан)",
          lambda d, b, i: None if i.get("executed") else f"{str(i.get('engine')).split()[0]} | {str(i.get('reason'))[:36]}", 20)

    import re

    def hour_of(i):
        m = re.search(r"(\d{1,2}):(\d{2})", str(i.get("t")))
        return int(m.group(1)) if m else None
    group("ЦАГААР (hub-ийн цаг, GMT+8 байж болно)", lambda d, b, i: (None if hour_of(i) is None else f"{hour_of(i):02d}"), 15)

    sl_ok = [(i, num(i.get("sl")), num(i.get("entry"))) for _, _, i in with_r if num(i.get("sl")) is not None and num(i.get("entry")) is not None]
    print(f"\n== SL-ийн мэдээлэл: R-тэй idea-аас sl-тэй нь {len(sl_ok)}")
    if len(sl_ok) >= 30:
        bk = defaultdict(list)
        for i, sl, en in sl_ok:
            dd = abs(en - sl)
            bk["a <3" if dd < 3 else "b 3-5" if dd < 5 else "c 5-8" if dd < 8 else "d >=8"].append(num(i["r"]))
        for k in sorted(bk):
            print(line("SL " + k[2:] + " цэг", bk[k]))

    print("\n== ӨДРӨӨР: [огноо  partial  n_setup]")
    print("  " + "  ".join(f"{r.get('date')}:{sum((b.get('n') or 0) for b in r.get('bots', []))}" for r in reports))

    last = reports[-1]
    print("\n== method (сүүлийн тайлан; үнэлгээний арга):")
    import textwrap
    print("\n".join(textwrap.wrap(str(last.get("method")), 110)[:12]))
    print("\n== headline (сүүлийн):", str(last.get("headline"))[:200])


if __name__ == "__main__":
    main()
