#!/usr/bin/env bash
# fill_backtest.sh - backtest.py-д "limit захиалга биелсэн үү" шалгалтыг ТУСГААРЛАГДСАН ХУУЛБАР дээр ажиллуулна.
# Live bot/контейнерт ХҮРЭХГҮЙ: эх .py файлуудыг хуулж, ХУУЛБАР дээр засвар хийнэ. Эх файл өөрчлөгдөхгүй.
#
#   A  baseline        - таны backtest.py яг одоогийнхоороо
#   B  fill шаардсан   - entry-д үнэ хүрсэн (12 цагийн дотор = live setup_pending_expiry_h) тохиолдолд л тооцно
#   C  fill + спрэд x2 - B + XAUUSD спрэд 0.30 -> 0.60
#
# Ажиллуулах:   bash fill_backtest.sh [ЭХЛЭХ] [ДУУСАХ]      (default 2025-12-15 2026-09-28)
# Хувьсагч:     SRC=/opt/bots/build/bot  DATA=.../data_bt  WORK=/root/bt_run  BT_SYMBOL=XAUUSD
set -euo pipefail

SRC="${SRC:-/opt/bots/build/bot}"
DATA="${DATA:-/opt/bots/data/a/wine/drive_c/data_bt}"
WORK="${WORK:-/root/bt_run}"
START="${1:-2025-12-15}"
END="${2:-2026-09-28}"
TIMEOUT="${TIMEOUT:-2400}"

[ -f "$SRC/backtest.py" ] || { echo "backtest.py олдсонгүй: $SRC"; exit 1; }
[ -f "$DATA/XAU_5m_data.csv" ] || { echo "өгөгдөл олдсонгүй: $DATA/XAU_5m_data.csv"; exit 1; }
command -v python3 >/dev/null || { echo "python3 байхгүй"; exit 1; }

mkdir -p "$WORK/src"
# зөвхөн .py ба playbook (json) - .env, лог, төлөвийн json-г хуулахгүй
cp "$SRC"/*.py "$WORK/src/"
[ -d "$SRC/playbook" ] && mkdir -p "$WORK/src/playbook" && cp "$SRC"/playbook/*.json "$WORK/src/playbook/" 2>/dev/null || true

if [ ! -x "$WORK/venv/bin/python" ]; then
  echo "[1/4] venv үүсгэж байна..."
  python3 -m venv "$WORK/venv" || { echo "python3-venv дутуу: apt install -y python3-venv   (дараа нь: rm -rf $WORK/venv)"; exit 1; }
fi
# өмнөх дутуу ажиллалтаас venv үлдсэн ч pandas/numpy байхгүй байж болно - импортоор шалгана
if ! "$WORK/venv/bin/python" -c "import pandas, numpy" >/dev/null 2>&1; then
  echo "[1/4] pandas/numpy суулгаж байна (нэг удаа, 1-3 минут)..."
  "$WORK/venv/bin/python" -m pip install -q pandas numpy || \
    { echo "pip суулгалт амжилтгүй. Интернэт/pip-г шалга: $WORK/venv/bin/python -m pip --version"; exit 1; }
fi
PY="$WORK/venv/bin/python"

# BT_SYMBOL: заагаагүй бол TАНЫ config.SYMBOLS-ийн эхний идэвхтэй түлхүүрийг авна (GOLD/XAUUSD хувилбарын ялгааг зохицуулна)
if [ -z "${BT_SYMBOL:-}" ]; then
  BT_SYMBOL="$(cd "$WORK/src" && "$PY" -c "import config;print(next((s for s,c in config.SYMBOLS.items() if c.get('enabled',True)), next(iter(config.SYMBOLS))))" 2>/dev/null || true)"
fi
export BT_SYMBOL
echo "BT_SYMBOL=${BT_SYMBOL:-<тодорхойгүй>}"

echo "[2/4] хуулбар дээр засвар хийж байна..."
"$PY" - "$WORK/src" <<'PYEOF'
import sys, os
d = sys.argv[1]
s = open(os.path.join(d, "backtest.py"), encoding="utf-8").read()
anchor = "jend=min(ei+HORIZON,i1); j=ei"
if s.count(anchor) != 1:
    sys.exit("ЗАНГУУ олдсонгүй эсвэл давхардсан (" + str(s.count(anchor)) + "): " + anchor +
             "\nТаны хувилбарын backtest.py өөр бүтэцтэй. Зогслоо, юу ч өөрчлөөгүй.")
i = s.index(anchor)
ls = s.rfind("\n", 0, i) + 1
indent = s[ls:i]
if indent.strip():
    sys.exit("зангуу мөрийн дундуур байна, зогслоо")
eol = s.index("\n", i)
block = """if os.environ.get("BT_REQUIRE_FILL","")=="1":
    fb=min(ei+int(os.environ.get("BT_FILL_BARS", str(720//TF_MIN[ENTRY_TF]))), jend)
    jf=ei
    while jf<=fb and not ((lo[jf]<=entry) if d=="bull" else (hi[jf]>=entry)):
        jf+=1
    if jf>fb:
        sk("no_fill"); continue
    j=jf
"""
block = "".join(indent + ln + "\n" for ln in block.splitlines())
patched = s[:eol + 1] + block + s[eol + 1:]
open(os.path.join(d, "backtest_fill.py"), "w", encoding="utf-8").write(patched)
import re
sp = re.sub(r'("XAUUSD"\s*:\s*)0\.30(\s*,\s*"GOLD"\s*:\s*)0\.30', r'\g<1>0.60\g<2>0.60', patched)
if sp == patched:
    print("АНХААР: спрэдийн мөр олдсонгүй, C хувилбар B-тэй ижил болно")
open(os.path.join(d, "backtest_fill_sp.py"), "w", encoding="utf-8").write(sp)
import py_compile
for f in ("backtest_fill.py", "backtest_fill_sp.py"):
    py_compile.compile(os.path.join(d, f), doraise=True)
print("засвар OK")
PYEOF

RUNPFX=(nice -n 19)
# нөөц хязгаарлах (live bot-уудыг хамгаалах). systemd-run ажиллаж байгааг эхлээд шалгана, үгүй бол зөвхөн nice.
if command -v systemd-run >/dev/null 2>&1 && [ "$(id -u)" = 0 ] \
   && systemd-run --scope --quiet -p MemoryMax=2G -- true >/dev/null 2>&1; then
  RUNPFX=(systemd-run --scope --quiet -p MemoryMax=2G -p CPUQuota=150% -- nice -n 19)
fi

run() {  # нэр, файл, FILL(0/1)
  local name="$1" file="$2" fill="$3"
  echo "[3/4] $name ажиллаж байна ($file)... (хэдэн минут болно)"
  ( cd "$WORK/src" && BT_BASE="$DATA" BT_REQUIRE_FILL="$fill" PYTHONUTF8=1 \
      timeout "$TIMEOUT" "${RUNPFX[@]}" "$PY" "$file" "$START" "$END" ) > "$WORK/out_$name.txt" 2>&1 || \
      echo "   ($name: алдаатай дууссан - $WORK/out_$name.txt-ийг харна уу)"
}
run A backtest.py 0
run B backtest_fill.py 1
run C backtest_fill_sp.py 1

echo
echo "[4/4] ХАРЬЦУУЛАЛТ ($START .. $END)"
for n in A B C; do
  case $n in A) t="A  baseline (одоогийн backtest)";; B) t="B  fill шаардсан";; C) t="C  fill + спрэд 0.60";; esac
  echo "----- $t"
  grep -E "candidate setup|Нийт арилжаа|Win rate|Gross R|NET R|Дундаж R|TP1/TP2/TP3|replay-skip|Traceback|Error|алга" "$WORK/out_$n.txt" | cut -c1-200 || echo "  (үр дүн алга)"
done
echo
echo "Бүтэн гаралт: $WORK/out_A.txt  out_B.txt  out_C.txt"
