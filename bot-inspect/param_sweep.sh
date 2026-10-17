#!/usr/bin/env bash
# param_sweep.sh - fill-тэй (live-ийн 12ц pending), бодит спрэд 0.55-тай backtest дээр sl_buffer x min_sl параметрүүдийг ЭРГЭЖ ХАРНА.
# fill_backtest.sh ажилласан байх ёстой (/root/bt_run/src/backtest_fill.py). Live bot-д ХҮРЭХГҮЙ, зөвхөн хуулбар дээр ажиллана.
# Нэг удаа candidate scan хийгээд олон параметрээр replay хийдэг тул хурдан.
#
# Ажиллуулах: bash param_sweep.sh [ЭХЛЭХ] [ДУУСАХ]      (default 2025-12-15 2026-09-28)
# Хувьсагч: WORK=/root/bt_run  DATA=.../data_bt  BT_SYMBOL=GOLD  SPREAD=0.55  FILL_BARS=144
set -euo pipefail
WORK="${WORK:-/root/bt_run}"
DATA="${DATA:-/opt/bots/data/a/wine/drive_c/data_bt}"
START="${1:-2025-12-15}"
END="${2:-2026-09-28}"
SPREAD="${SPREAD:-0.55}"
FILL_BARS="${FILL_BARS:-144}"
TIMEOUT="${TIMEOUT:-3000}"
PY="$WORK/venv/bin/python"

[ -f "$WORK/src/backtest_fill.py" ] || { echo "$WORK/src/backtest_fill.py алга - эхлээд fill_backtest.sh ажиллуулна уу"; exit 1; }
[ -x "$PY" ] || { echo "$PY алга"; exit 1; }

if [ -z "${BT_SYMBOL:-}" ]; then
  BT_SYMBOL="$(cd "$WORK/src" && "$PY" -c "import config;print(next((s for s,c in config.SYMBOLS.items() if c.get('enabled',True)), next(iter(config.SYMBOLS))))" 2>/dev/null || true)"
fi
export BT_SYMBOL
echo "BT_SYMBOL=$BT_SYMBOL  spread=$SPREAD  fill_bars=$FILL_BARS"

"$PY" - "$WORK/src" "$SPREAD" <<'PYEOF'
import sys, os, py_compile
d, spread = sys.argv[1], sys.argv[2]
s = open(os.path.join(d, "backtest_fill.py"), encoding="utf-8").read()
anchor = "        rows=[]\n        for name,p in variants:"
if s.count(anchor) != 1:
    sys.exit("ЗАНГУУ олдсонгүй (sweep хэсэг) - таны хувилбар өөр бүтэцтэй. Зогслоо, юу ч өөрчлөөгүй.")
block = (
    "        if os.environ.get('BT_EXTRA')=='1':\n"
    "            variants=[(f'buf{b} minsl{m}', {**base,'sl_buffer':b,'min_sl':m,'spread':float(os.environ.get('BT_SPREAD','" + spread + "'))})\n"
    "                      for b in (0.5,1.0,2.0) for m in (20,30,40,60,80,100)]\n"
)
i = s.index(anchor)
open(os.path.join(d, "backtest_sweep.py"), "w", encoding="utf-8").write(s[:i] + block + s[i:])
py_compile.compile(os.path.join(d, "backtest_sweep.py"), doraise=True)
print("засвар OK")
PYEOF

OUT="$WORK/out_sweep.txt"
echo "ажиллаж байна (хэдэн минут)... -> $OUT"
( cd "$WORK/src" && BT_BASE="$DATA" BT_REQUIRE_FILL=1 BT_FILL_BARS="$FILL_BARS" BT_EXTRA=1 BT_SPREAD="$SPREAD" PYTHONUTF8=1 \
    timeout "$TIMEOUT" nice -n 19 "$PY" backtest_sweep.py "$START" "$END" sweep ) > "$OUT" 2>&1 || echo "(алдаатай дууссан - $OUT-ийг харна уу)"
echo
echo "== sl_buffer x min_sl (fill + спрэд $SPREAD)   [min_sl нэгж: pip, 10 pip = 1.0 цэг]"
grep -E "^param|^buf|Traceback|Error|алга" "$OUT" | cut -c1-120
