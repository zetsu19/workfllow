#!/usr/bin/env bash
# Oracle (Сервер бот + hub): нууцгүй, унших-л өдөр тутмын экспорт.
# Суулгах: bash export_oracle.sh --install-cron   (өдөр бүр 06:10)
# Гарц: ~/export/oracle_latest.tgz  (өөр юу ч өөрчлөхгүй, bot/hub-д хүрэхгүй)
set -u
umask 077
TRADE=${TRADE:-/home/ubuntu/Trade}
HUB=${HUB:-$HOME/hub}
OUT=${OUT:-$HOME/export}
DAYS=${DAYS:-14}
KEEP_DAYS=${KEEP_DAYS:-14}
WINE_PY=${WINE_PY:-/home/ubuntu/.mt5/drive_c/Python312/python.exe}
SYMBOL=${SYMBOL:-GOLD}
SELF=$(readlink -f "$0")

if [ "${1:-}" = "--install-cron" ]; then
  mkdir -p "$OUT"
  ( crontab -l 2>/dev/null | grep -v 'export_oracle.sh'
    echo "10 6 * * * $SELF >> $OUT/cron.log 2>&1" ) | crontab -
  echo "cron суулгалаа:"; crontab -l | grep export_oracle.sh
  exit 0
fi

STAMP=$(date +%Y%m%d_%H%M)
D=$OUT/oracle_$STAMP
mkdir -p "$D"
LOG=$D/manifest.txt
{ echo "host=$(hostname) time=$(date -Is) days=$DAYS"; } > "$LOG"

scrub() {  # scrub <in> <out>: нууц/дансны түлхүүрүүдийг устгана (json эсвэл jsonl)
  python3 - "$1" "$2" <<'PY'
import json, sys
BAD = ("password", "passwd", "token", "secret", "apikey", "api_key", "login", "account")
def clean(o):
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items() if not any(b in k.lower() for b in BAD)}
    if isinstance(o, list):
        return [clean(v) for v in o]
    return o
src, dst = sys.argv[1], sys.argv[2]
txt = open(src, encoding="utf-8").read()
with open(dst, "w", encoding="utf-8") as f:
    try:
        f.write(json.dumps(clean(json.loads(txt)), ensure_ascii=False))
    except ValueError:
        for line in txt.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                f.write(json.dumps(clean(json.loads(line)), ensure_ascii=False) + "\n")
            except ValueError:
                pass
PY
}

# 1. Bot-ийн бодит арилжаа ба шийдвэрүүд
[ -f "$TRADE/trade_ledger.jsonl" ] && scrub "$TRADE/trade_ledger.jsonl" "$D/ledger.jsonl"
[ -f "$TRADE/ml_decisions.jsonl" ] && scrub "$TRADE/ml_decisions.jsonl" "$D/ml_decisions.jsonl"
for f in setup_stats.json setup_pending.json; do
  [ -f "$TRADE/$f" ] && scrub "$TRADE/$f" "$D/$f"
done

# 2. Hub: бүх bot-ийн idea, сүүлийн DAYS өдрийн тайлан
[ -f "$HUB/data/hub_ideas.csv" ] && cp "$HUB/data/hub_ideas.csv" "$D/hub_ideas.csv"
if [ -d "$HUB/data/reports" ]; then
  mkdir -p "$D/reports"
  find "$HUB/data/reports" -maxdepth 1 -name '*.json' -mtime -"$DAYS" -print0 |
    while IFS= read -r -d '' f; do scrub "$f" "$D/reports/$(basename "$f")"; done
fi

# 3. MT5-аас M1/M5 баар (унших-л; ажиллаж буй terminal-д холбогдоно)
if [ -f "$WINE_PY" ]; then
  PYF=$(mktemp /tmp/export_bars_XXXX.py)
  cat > "$PYF" <<PY
import os
import MetaTrader5 as mt5
from datetime import datetime, timedelta
if not mt5.initialize():
    raise SystemExit("init failed: %s" % (mt5.last_error(),))
sym = os.environ.get("EXP_SYMBOL", "GOLD")
mt5.symbol_select(sym, True)
b = datetime.utcnow() + timedelta(hours=6)
a = b - timedelta(days=int(os.environ.get("EXP_DAYS", "14")))
out = os.environ["EXP_OUT"]
for name, tf in (("m1", mt5.TIMEFRAME_M1), ("m5", mt5.TIMEFRAME_M5)):
    r = mt5.copy_rates_range(sym, tf, a, b)
    n = 0 if r is None else len(r)
    print(name, n)
    if n:
        with open("Z:" + out + "/bars_%s.csv" % name, "w") as f:
            f.write("time;open;high;low;close;spread\n")
            for x in r:
                t = datetime.utcfromtimestamp(int(x["time"])).strftime("%Y.%m.%d %H:%M")
                f.write("%s;%s;%s;%s;%s;%s\n" % (t, x["open"], x["high"], x["low"], x["close"], x["spread"]))
mt5.shutdown()
PY
  EXP_OUT="$D" EXP_DAYS="$DAYS" EXP_SYMBOL="$SYMBOL" \
  WINEPREFIX=/home/ubuntu/.mt5 WINEARCH=win64 WINEDEBUG=-all DISPLAY=:99 \
    timeout 240 wine "$WINE_PY" "$PYF" 2>&1 | tail -3 >> "$LOG"
  rm -f "$PYF"
else
  echo "bars: WINE_PY олдсонгүй, алгаслаа" >> "$LOG"
fi

# 4. Нууцын шалгалт: тохирсон файлыг тарилгаас хасна
BADRE='password|passwd|secret|api[_-]?key|push_token|bot[0-9]{6,}:[A-Za-z0-9_-]{20,}'
grep -rIlEi "$BADRE" "$D" 2>/dev/null | grep -v '/manifest.txt$' | while read -r f; do
  echo "REMOVED (нууц төстэй): ${f#$D/}" >> "$LOG"; rm -f "$f"
done

( cd "$D" && for f in $(find . -type f | sort); do printf '%s %s\n' "$(stat -c %s "$f")" "$f"; done ) >> "$LOG"
tar czf "$OUT/oracle_$STAMP.tgz" -C "$OUT" "oracle_$STAMP"
cp "$OUT/oracle_$STAMP.tgz" "$OUT/oracle_latest.tgz"
rm -rf "$D"
find "$OUT" -maxdepth 1 -name 'oracle_2*.tgz' -mtime +"$KEEP_DAYS" -delete
echo "OK $OUT/oracle_latest.tgz ($(du -h "$OUT/oracle_latest.tgz" | cut -f1))"
