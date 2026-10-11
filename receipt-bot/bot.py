"""Telegram группт ирсэн падангийн зургийг Excel болгож буцаах бот.
OCR нь локал Tesseract (үнэгүй, токен зарцуулдаггүй)."""
import logging
import os
import asyncio
from datetime import date

from telegram import Update
from telegram.ext import Application, ContextTypes, CommandHandler, MessageHandler, filters

from excel import append_items
from ocr import read_receipt
from receipt_parser import find_date

DATA_DIR = os.environ.get("DATA_DIR", "data")
LANGS = os.environ.get("OCR_LANGS", "mon+eng")
ALLOWED = {int(x) for x in os.environ.get("ALLOWED_CHAT_IDS", "").split(",") if x.strip()}
os.makedirs(DATA_DIR, exist_ok=True)
log = logging.getLogger("receipt-bot")


def xlsx_path(chat_id: int) -> str:
    return os.path.join(DATA_DIR, f"purchases_{chat_id}.xlsx")


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
    items, gtotal, matched, rdate = await asyncio.to_thread(read_receipt, data)
    d = find_date(msg.caption or "") or rdate or msg.date.date()
    if not items:
        await msg.reply_text("Падангаас мөр танилгүй. Илүү тод, шулуун зураг явуулна уу.")
        return
    path = xlsx_path(msg.chat_id)
    append_items(path, d, items)
    total = sum(i.total for i in items)
    note = ""
    if gtotal and not matched:
        note = f"\n⚠️ Падан дээрх нийт {gtotal:,.0f}₮ ≠ танисан {total:,.0f}₮ — Excel-ийг шалгана уу."
    await msg.reply_text(f"✅ {len(items)} мөр нэмлээ ({d:%d/%m/%Y}), нийт {total:,.0f}₮{note}")
    with open(path, "rb") as fh:
        await msg.reply_document(fh, filename=f"purchases_{date.today():%Y%m%d}.xlsx")


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
    await update.message.reply_text("Шинэ Excel эхэллээ (өмнөхийг .bak болгож хадгаллаа).")


def main():
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)  # URL дотор token байдаг
    app = Application.builder().token(os.environ["BOT_TOKEN"]).build()
    app.add_handler(CommandHandler("excel", cmd_excel))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, on_photo))
    app.run_polling()


if __name__ == "__main__":
    main()
