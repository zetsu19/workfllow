#!/usr/bin/env bash
# Contabo (bot-a..d, Docker): нууцгүй, унших-л өдөр тутмын экспорт.
# Суулгах: bash export_contabo.sh --install-cron   (өдөр бүр 06:20)
# Гарц: ~/export/contabo_latest.tgz
set -u
umask 077
BOTS=${BOTS:-/opt/bots}
OUT=${OUT:-$HOME/export}
KEEP_DAYS=${KEEP_DAYS:-14}
MAXMB=${MAXMB:-30}
SELF=$(readlink -f "$0")

if [ "${1:-}" = "--install-cron" ]; then
  mkdir -p "$OUT"
  ( crontab -l 2>/dev/null | grep -v 'export_contabo.sh'
    echo "20 6 * * * $SELF >> $OUT/cron.log 2>&1" ) | crontab -
  echo "cron суулгалаа:"; crontab -l | grep export_contabo.sh
  exit 0
fi

STAMP=$(date +%Y%m%d_%H%M)
D=$OUT/contabo_$STAMP
mkdir -p "$D/trades"
LOG=$D/manifest.txt
{ echo "host=$(hostname) time=$(date -Is)"; } > "$LOG"

scrub() {
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

# 1. Bot бүрийн арилжааны ledger
if [ -d "$BOTS/trades" ]; then
  for f in "$BOTS"/trades/*.json "$BOTS"/trades/*.jsonl; do
    [ -f "$f" ] && scrub "$f" "$D/trades/$(basename "$f")"
  done
fi

# 2. ML: нэгтгэсэн pool ба journal sqlite (хэт том бол алгасна)
[ -f "$BOTS/ml_pool.json" ] && scrub "$BOTS/ml_pool.json" "$D/ml_pool.json"
mkdir -p "$D/ml"
find "$BOTS" -type f \( -name '*.sqlite' -o -name '*.sqlite3' -o -name '*.db' \) \
     -path '*ml*' -size -"${MAXMB}"M -not -path '*/wine/*' -print0 2>/dev/null |
  while IFS= read -r -d '' f; do
    n=$(echo "${f#$BOTS/}" | tr '/' '_')
    cp "$f" "$D/ml/$n"
  done

# 3. Нууцын шалгалт (text файлд)
BADRE='password|passwd|secret|api[_-]?key|push_token|bot[0-9]{6,}:[A-Za-z0-9_-]{20,}'
grep -rIlEi "$BADRE" "$D" 2>/dev/null | grep -v '/manifest.txt$' | while read -r f; do
  echo "REMOVED (нууц төстэй): ${f#$D/}" >> "$LOG"; rm -f "$f"
done

( cd "$D" && for f in $(find . -type f | sort); do printf '%s %s\n' "$(stat -c %s "$f")" "$f"; done ) >> "$LOG"
tar czf "$OUT/contabo_$STAMP.tgz" -C "$OUT" "contabo_$STAMP"
cp "$OUT/contabo_$STAMP.tgz" "$OUT/contabo_latest.tgz"
rm -rf "$D"
find "$OUT" -maxdepth 1 -name 'contabo_2*.tgz' -mtime +"$KEEP_DAYS" -delete
echo "OK $OUT/contabo_latest.tgz ($(du -h "$OUT/contabo_latest.tgz" | cut -f1))"
