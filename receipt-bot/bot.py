"""Telegram группт ирсэн падангийн зургийг Excel болгож буцаах бот.
Давхарга: 1) локал OCR (үнэгүй) -> 2) нийт дүн таараагүй бол Claude Haiku 5.5 vision
-> 3) Haiku таараагүй бол Sonnet 5.5 -> 4) /fix засвараас суралцана."""
import asyncio
import logging
import os
import re
from datetime import date

from telegram import Update
from telegram.ext import Application, ContextTypes, CommandHandler, MessageHandler, filters

import ai_vision
from excel import append_items, update_row
from memory import Memory
from ocr import read_receipt
from receipt_parser import find_date

DATA_DIR = os.environ.get("DATA_DIR", "data")
ALLOWED = {int(x) for x in os.environ.get("ALLOWED_CHAT_IDS", "").split(",") if x.strip()}
os.makedirs(DATA_DIR, exist_ok=True)
log = logging.getLogger("receipt-bot")


def xlsx_path(chat_id: int) -> str:
    return os.path.join(DATA_DIR, f"purchases_{chat_id}.xlsx")


def mem_of(chat_id: int) -> Memory:
    return Memory(os.path.join(DATA_DIR, f"memory_{chat_id}.json"))


def _fmt(n):
    return f"{n:,.0f}" if float(n).is_integer() else f"{n:,.2f}"


async def on_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if ALLOWED and msg.chat_id not in ALLOWED:
        return
    if msg.photo:
        f = await msg.photo[-1].get_file()
    elif msg.document and (msg.document.mime_type or "").startswith("image/"):
        f = await msg.document.get_file()
    else:
        return
    data = bytes(await f.download_as_bytearray())
    mem = mem_of(msg.chat_id)

    # 1-р давхарга: локал OCR
    items, gtotal, matched, rdate = await asyncio.to_thread(read_receipt, data)
    source, store = "OCR", None
    # 2-3-р давхарга: нийт дүн таараагүй бол AI
    if not matched and ai_vision.available():
        try:
            res = await asyncio.to_thread(ai_vision.read_with_ai, data, mem.hints())
        except Exception:
            log.exception("AI failed")
            res = None
        if res:
            items, gtotal, matched, adate, model, store = res
            rdate, source = adate or rdate, f"AI ({model})"
    if not items:
        await msg.reply_text("Падангаас мөр танилгүй. Илүү тод, шулуун зураг (Файл хэлбэрээр) явуулна уу.")
        return

    mem.apply(items)
    d = find_date(msg.caption or "") or rdate or msg.date.date()
    path = xlsx_path(msg.chat_id)
    cap = (msg.caption or "").strip()
    store = store or (cap if cap and not find_date(cap) else None)  # caption-д дэлгүүрийн нэр бичиж болно
    first = append_items(path, d, items, store)
    mem.d["last"] = {"start": first, "count": len(items)}
    if matched:  # нийт дүнтэй таарсан л бол барааны жагсаалтад нэмж суралцана
        mem.remember(items)
    mem.save()

    total = sum(i.total for i in items)
    lines = [f"{n}. {i.name} — {_fmt(i.qty)} × {_fmt(i.price)} = {_fmt(i.total)}" for n, i in enumerate(items, 1)]
    head = f"✅ {len(items)} мөр нэмлээ ({d:%d/%m/%Y}){" · " + store if store else ""}, нийт {total:,.0f}₮ · {source}"
    if gtotal and not matched:
        head += f"\n⚠️ Падан дээрх нийт {gtotal:,.0f}₮ ≠ танисан {total:,.0f}₮ — шалгана уу. Засах: /fix <дугаар> <нэр> [qty=2 price=5000]"
    await msg.reply_text(head + "\n" + "\n".join(lines)[:3500])
    with open(path, "rb") as fh:
        await msg.reply_document(fh, filename=f"purchases_{date.today():%Y%m%d}.xlsx")


async def cmd_fix(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/fix 3 Valhalla Herb liqueur 35%   |   /fix 2 qty=3 price=66000"""
    msg = update.effective_message
    if ALLOWED and msg.chat_id not in ALLOWED:
        return
    args = ctx.args or []
    mem = mem_of(msg.chat_id)
    last = mem.d["last"]
    if len(args) < 2 or not args[0].isdigit() or not 1 <= int(args[0]) <= last["count"]:
        await msg.reply_text(f"Хэрэглээ: /fix <дугаар 1-{last['count']}> <шинэ нэр> [qty=2] [price=5000]")
        return
    kv, words = {}, []
    for a in args[1:]:
        m = re.fullmatch(r"(qty|price)=([\d.,]+)", a)
        if m:
            kv[m.group(1)] = float(m.group(2).replace(",", ""))
        else:
            words.append(a)
    name = " ".join(words) or None
    row = last["start"] + int(args[0]) - 1
    old = update_row(xlsx_path(msg.chat_id), row, name, kv.get("qty"), kv.get("price"), (last["start"], last["count"]))
    if old is None:
        await msg.reply_text("Мөр олдсонгүй.")
        return
    if name and old and name != old:
        mem.learn(old, name)
        mem.save()
    await msg.reply_text(f"✏️ {args[0]}-р мөр засагдлаа." + (" Дараагийн удаа энэ нэрийг автоматаар солино." if name else ""))


async def cmd_excel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    p = xlsx_path(update.effective_chat.id)
    if not os.path.exists(p):
        await update.message.reply_text("Одоогоор бүртгэл алга.")
        return
    with open(p, "rb") as fh:
        await update.message.reply_document(fh)


async def cmd_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    p = xlsx_path(update.effective_chat.id)
    if os.path.exists(p):
        os.replace(p, p + ".bak")
    m = mem_of(update.effective_chat.id)
    m.d["last"] = {"start": 0, "count": 0}
    m.save()
    await update.message.reply_text("Шинэ Excel эхэллээ (өмнөхийг .bak болгож хадгаллаа).")


def main():
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)  # URL дотор token байдаг
    app = Application.builder().token(os.environ["BOT_TOKEN"]).build()
    app.add_handler(CommandHandler("excel", cmd_excel))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("fix", cmd_fix))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, on_photo))
    log.info("AI vision: %s", ai_vision.MODELS if ai_vision.available() else "off (ANTHROPIC_API_KEY байхгүй)")
    app.run_polling()


if __name__ == "__main__":
    main()
