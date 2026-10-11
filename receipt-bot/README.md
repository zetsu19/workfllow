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

## AI давхарга (заавал биш) ба суралцах
1. Локал OCR нийт дүнтэй таарвал AI дуудахгүй (үнэгүй).
2. Таараагүй бол **Claude Haiku 5.5** vision, түүнээс ч таараагүй бол **Sonnet 5.5** (`AI_MODELS`-оор өөрчилнө). `ANTHROPIC_API_KEY`-г `.env`-д өгвөл идэвхжинэ; өгөөгүй бол зөвхөн OCR.
3. Засвараас суралцах: `/fix 3 Valhalla Herb liqueur 35%` (эсвэл `/fix 2 qty=3 price=66000`) — Excel-ийн мөрийг засаж, нэрийг дараагийн падаанд автоматаар солино, мөн AI-д "өмнө худалдаж авсан бараа" гэж зөвлөмж болгож өгнө. (Загварыг fine-tune хийдэггүй; санах ой `data/memory_<chat>.json`.)

Тест: `python test_parser.py && python test_ai_mock.py`
