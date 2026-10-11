# Падан → Excel Telegram бот

Группт ирсэн худалдан авалтын падангийн зургийг OCR-ээр уншиж, Excel-д (Огноо | нэр | нэмжих нэгж | тоо | нэгжийн үнэ | Нийт дүн) мөр болгон нэмээд бүлэг рүү буцаан илгээнэ. Шинэ мөрүүд цэнхэр өнгөтэй. **Токен/API зардалгүй** — локал Tesseract ашиглана.

## Ажиллуулах
1. @BotFather-аар бот үүсгэж token авна; `/setprivacy` → Disable (группын зургийг харахын тулд), ботыг группт нэмнэ.
2. `docker build -t receipt-bot . && docker run -d --restart=always -e BOT_TOKEN=xxx -e ALLOWED_CHAT_IDS=-100123 -v $PWD/data:/app/data receipt-bot`
   (Docker-гүйгээр: `apt install tesseract-ocr tesseract-ocr-mon`, `pip install -r requirements.txt`, `BOT_TOKEN=xxx python bot.py`)

## Команд
- зураг явуулах → мөр нэмээд Excel буцаана (зургийн caption-д огноо бичвэл ашиглана, үгүй бол падан дээрх огноо/өнөөдөр)
- `/excel` — нийт файлыг авах, `/reset` — шинэ файл эхлэх

Тест: `python test_parser.py`
