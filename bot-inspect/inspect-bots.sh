#!/usr/bin/env bash
# inspect-bots.sh - systemd bot-уудын бүтэц, логик, лог, trade түүхийг УНШИЖ тайлан үүсгэнэ.
# Зөвхөн унших (read-only): юуг ч өөрчлөхгүй, устгахгүй, дахин ачаалахгүй.
# Нууц мэдээллийг (key, token, password, IP) автоматаар нууна.
#
# Ажиллуулах:
#   bash inspect-bots.sh                    # /etc/systemd/system доторх бүх custom service
#   bash inspect-bots.sh gold-bot tg-bot    # зөвхөн нэр заасан service-үүд
# Үр дүн: ~/bot-report-<огноо>.txt

set -u
OUT="${HOME}/bot-report-$(date +%Y%m%d-%H%M%S).txt"
MAX_FILE_LINES=250      # нэг файлаас авах дээд мөр
MAX_LOG_LINES=120       # journal-ийн мөр
SERVICES=("$@")

# ---------- нууц нуух ----------
redact() {
  sed -E \
    -e 's/(sk-ant-[A-Za-z0-9_-]{6})[A-Za-z0-9_-]+/\1<HIDDEN>/g' \
    -e 's/[0-9]{8,10}:[A-Za-z0-9_-]{30,}/<TELEGRAM_TOKEN_HIDDEN>/g' \
    -e 's/((pass(word|wd)?|pwd|secret|token|api[_-]?key|apikey|auth|login|account|private[_-]?key|credential|bearer)[A-Za-z0-9_"'\'' ]*[:=][ ]*)[^ ,;)}]+/\1<HIDDEN>/Ig' \
    -e 's/([A-Za-z0-9+\/=_-]{40,})/<LONG_STRING_HIDDEN>/g' \
    -e 's/\b([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})\b/x.x.\3.\4/g'
}

# нууц файлыг огт унших хориглосон жагсаалт
is_secret_file() {
  case "$(basename "$1")" in
    .env|.env.*|*.pem|*.key|*.p12|*.pfx|id_rsa*|*.kdbx|credentials*|secrets*|*.token) return 0 ;;
  esac
  return 1
}

section() { printf '\n\n==================== %s ====================\n' "$1"; }
sub()     { printf '\n---- %s ----\n' "$1"; }

report() {
  section "СИСТЕМ"
  date; uname -sr; uptime
  free -h
  df -h / | tail -n +1
  nproc

  # ---------- service олох ----------
  if [ ${#SERVICES[@]} -eq 0 ]; then
    mapfile -t SERVICES < <(ls /etc/systemd/system/*.service 2>/dev/null | xargs -n1 -r basename | sed 's/\.service$//')
  fi
  section "ОЛДСОН SERVICE-ҮҮД"
  printf '%s\n' "${SERVICES[@]:-<олдсонгүй>}"
  sub "Ажиллаж буй байдал"
  for s in "${SERVICES[@]}"; do
    printf '%-35s %s\n' "$s" "$(systemctl is-active "$s" 2>/dev/null)"
  done

  declare -A SEEN_DIRS=()

  for s in "${SERVICES[@]}"; do
    section "SERVICE: $s"
    sub "systemctl cat"
    systemctl cat "$s" 2>/dev/null | redact
    sub "status (богино)"
    systemctl status "$s" --no-pager -n 0 2>/dev/null | redact | head -15
    sub "Нөөцийн хэрэглээ"
    systemctl show "$s" -p MemoryCurrent -p CPUUsageNSec -p ActiveEnterTimestamp -p NRestarts 2>/dev/null
    sub "Сүүлийн лог (journal, ${MAX_LOG_LINES} мөр)"
    journalctl -u "$s" -n "$MAX_LOG_LINES" --no-pager 2>/dev/null | redact

    WD="$(systemctl show "$s" -p WorkingDirectory --value 2>/dev/null)"
    EXEC="$(systemctl show "$s" -p ExecStart --value 2>/dev/null | grep -oE 'path=[^ ;]+' | head -1 | cut -d= -f2)"
    ARGS="$(systemctl show "$s" -p ExecStart --value 2>/dev/null | grep -oE 'argv\[\]=[^;]+' | head -1 | sed 's/argv\[\]=//')"
    [ -z "$WD" ] || [ "$WD" = "/" ] && WD="$(dirname "$(echo "$ARGS" | tr ' ' '\n' | grep -E '\.(py|js|sh|mq5)$' | head -1)" 2>/dev/null)"
    [ -d "$WD" ] || { echo "(WorkingDirectory олдсонгүй: '$WD')"; continue; }
    [ -n "${SEEN_DIRS[$WD]:-}" ] && { echo "(хавтас $WD өмнө нь шалгагдсан)"; continue; }
    SEEN_DIRS[$WD]=1

    section "ХАВТАС: $WD"
    sub "Бүтэц"
    ls -la "$WD" 2>/dev/null
    sub "Файлууд (гүн 3, node_modules/.git/venv-гүй)"
    find "$WD" -maxdepth 3 -type f \
      -not -path '*/node_modules/*' -not -path '*/.git/*' -not -path '*/venv/*' \
      -not -path '*/.venv/*' -not -path '*/__pycache__/*' 2>/dev/null \
      -printf '%TY-%Tm-%Td %TH:%TM  %8s  %p\n' | sort -k3 | head -150
    sub "Кодын мөрийн тоо"
    find "$WD" -maxdepth 3 -type f \( -name '*.py' -o -name '*.js' -o -name '*.ts' -o -name '*.mq5' -o -name '*.mq4' -o -name '*.go' \) \
      -not -path '*/node_modules/*' -not -path '*/venv/*' -not -path '*/.venv/*' 2>/dev/null \
      -exec wc -l {} + 2>/dev/null | sort -rn | head -20
    sub "Хамаарал (requirements / package.json)"
    for f in requirements.txt package.json pyproject.toml; do
      [ -f "$WD/$f" ] && { echo "# $f"; redact < "$WD/$f" | head -40; }
    done
    sub "README / тэмдэглэл"
    for f in README.md README.txt NOTES.md; do
      [ -f "$WD/$f" ] && { echo "# $f"; redact < "$WD/$f" | head -60; }
    done

    sub "Арилжааны логикийн түлхүүр үгс (файл:мөр)"
    grep -rnIE 'XAUUSD|GOLD|buy|sell|stop_?loss|take_?profit|\bsl\b|\btp\b|lot|volume|risk|leverage|trailing|breakeven|spread|rsi|ema|sma|macd|atr|bollinger|supertrend|timeframe|signal|entry|exit' \
      --include='*.py' --include='*.js' --include='*.ts' --include='*.mq5' --include='*.mq4' --include='*.json' --include='*.yaml' --include='*.yml' --include='*.ini' --include='*.cfg' \
      --exclude-dir=node_modules --exclude-dir=venv --exclude-dir=.venv --exclude-dir=.git --exclude-dir=__pycache__ \
      "$WD" 2>/dev/null | redact | head -150

    sub "Тохиргооны файлууд (нууц нуугдсан)"
    find "$WD" -maxdepth 2 -type f \( -name 'config*' -o -name 'settings*' -o -name '*.ini' -o -name '*.cfg' -o -name '*.yaml' -o -name '*.yml' \) \
      -not -path '*/node_modules/*' -not -path '*/venv/*' 2>/dev/null | while read -r f; do
        is_secret_file "$f" && { echo "# $f  (нууц файл - алгассан)"; continue; }
        echo "# $f"; redact < "$f" | head -60
      done

    sub "Гол код (эхний ${MAX_FILE_LINES} мөр, том 5 файл)"
    find "$WD" -maxdepth 3 -type f \( -name '*.py' -o -name '*.js' -o -name '*.ts' -o -name '*.mq5' -o -name '*.mq4' \) \
      -not -path '*/node_modules/*' -not -path '*/venv/*' -not -path '*/.venv/*' -not -path '*/__pycache__/*' 2>/dev/null \
      -printf '%s %p\n' | sort -rn | head -5 | cut -d' ' -f2- | while read -r f; do
        is_secret_file "$f" && continue
        echo; echo "######## $f ########"
        redact < "$f" | head -n "$MAX_FILE_LINES"
      done

    sub "Лог файлууд (сүүлийн 60 мөр)"
    find "$WD" -maxdepth 3 -type f \( -name '*.log' -o -name '*.log.*' \) 2>/dev/null | head -5 | while read -r f; do
      echo "# $f"; tail -n 60 "$f" | redact
    done

    sub "Trade/түүхийн файлууд (CSV, JSON, SQLite)"
    find "$WD" -maxdepth 3 -type f \( -iname '*trade*' -o -iname '*order*' -o -iname '*history*' -o -iname '*deal*' -o -iname '*.csv' -o -iname '*.db' -o -iname '*.sqlite*' \) \
      -not -path '*/node_modules/*' -not -path '*/venv/*' 2>/dev/null | head -15 | while read -r f; do
        is_secret_file "$f" && continue
        echo; echo "# $f  ($(stat -c %s "$f") bytes)"
        case "$f" in
          *.db|*.sqlite|*.sqlite3)
            if command -v sqlite3 >/dev/null; then
              sqlite3 -readonly "$f" ".tables" 2>/dev/null
              for t in $(sqlite3 -readonly "$f" ".tables" 2>/dev/null); do
                echo "-- $t: $(sqlite3 -readonly "$f" "SELECT COUNT(*) FROM \"$t\";" 2>/dev/null) мөр"
                sqlite3 -readonly -header "$f" "SELECT * FROM \"$t\" ORDER BY rowid DESC LIMIT 15;" 2>/dev/null | redact
              done
            else echo "(sqlite3 суугаагүй: sudo apt install sqlite3)"; fi ;;
          *.csv) head -1 "$f" | redact; echo "..."; tail -n 25 "$f" | redact; echo "мөрийн тоо: $(wc -l < "$f")" ;;
          *.json) head -c 3000 "$f" | redact ;;
          *) head -n 20 "$f" | redact ;;
        esac
      done
  done

  section "ПРОЦЕССҮҮД (RAM-аар)"
  ps aux --sort=-%mem | head -12 | redact
  section "ИДЭВХТЭЙ ПОРТУУД"
  ss -tlnp 2>/dev/null | redact
  section "CRON"
  crontab -l 2>/dev/null | redact || true
  ls /etc/cron.d 2>/dev/null

  section "ДУУСЛАА"
  echo "Тайлан: $OUT"
}

report > "$OUT" 2>&1
chmod 600 "$OUT"
echo "Тайлан үүслээ: $OUT ($(wc -c < "$OUT") bytes, $(wc -l < "$OUT") мөр)"
echo
echo "АНХААР: Илгээхээсээ өмнө шалгаарай:"
echo "  grep -niE 'pass|token|secret|key|login' \"$OUT\" | head -30"
