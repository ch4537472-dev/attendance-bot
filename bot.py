import os
import logging
from datetime import datetime
import httpx
from google import genai
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ChatAction

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
GEMINI_KEY     = os.environ["GEMINI_API_KEY"]
SHEET_ID       = os.environ["SHEET_ID"]import os
import asyncio
import logging
from datetime import datetime
import httpx
import anthropic
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ChatAction

# ── Logging ──────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────
TELEGRAM_TOKEN   = os.environ["8602240535:AAGGkzTOMHDGwEaiD28V2Z8zXFHioGhtRAQ"]
ANTHROPIC_KEY    = os.environ["AIzaSyAOZLW_J2BX7GezNfpcGdW4aX9R8am4ZgQ"]
SHEET_ID         = os.environ["1FWPETJzYvVT-Uj5DodxkqFxN8pXkKpEKTrh28ejCQv0"]           # Google Sheet ID فقط
SHEET_GID        = os.environ.get("1713280853", "0") # رقم الصفحة (gid)

SHEET_CSV_URL = (
    f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
    f"/export?format=csv&gid={SHEET_GID}"
)

claude = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

# ── Fetch Sheet Data ──────────────────────────────────────
async def fetch_sheet() -> str:
    """جيب بيانات الشيت كـ CSV نص"""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(SHEET_CSV_URL)
            r.raise_for_status()
            return r.text
    except Exception as e:
        logger.error(f"Sheet fetch error: {e}")
        return ""

def parse_attendance(csv_text: str) -> dict:
    """حوّل CSV لإحصائيات بسيطة"""
    lines = [l for l in csv_text.strip().splitlines() if l.strip()]
    employees = []
    for line in lines:
        cols = line.split(",")
        if not cols:
            continue
        name_cell = cols[0].strip().strip('"')
        # تجاهل الصفوف الفارغة أو صفوف الفورمولا
        if not name_cell or name_cell.startswith("=") or name_cell.startswith("http"):
            continue
        status_cell = cols[1].strip().strip('"') if len(cols) > 1 else ""
        present = "✔" in status_cell or status_cell.lower() in ("1", "true", "yes", "حاضر", "present")
        employees.append({"name": name_cell, "present": present})

    total   = len(employees)
    present = sum(1 for e in employees if e["present"])
    absent  = total - present
    pct     = round((present / total) * 100) if total else 0

    return {
        "total": total,
        "present": present,
        "absent": absent,
        "pct": pct,
        "employees": employees,
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }

# ── Ask Claude ────────────────────────────────────────────
async def ask_claude(user_question: str, attendance: dict) -> str:
    present_names = [e["name"] for e in attendance["employees"] if e["present"]]
    absent_names  = [e["name"] for e in attendance["employees"] if not e["present"]]

    system_prompt = f"""أنت مساعد ذكي متخصص في شيت الحضور والغياب.
البيانات محدّثة تلقائياً من Google Sheets (آخر تحديث: {attendance['fetched_at']}).

📊 إحصائيات اليوم:
- إجمالي الموظفين: {attendance['total']}
- الحاضرون: {attendance['present']} ({attendance['pct']}%)
- الغائبون: {attendance['absent']} ({100 - attendance['pct']}%)

✅ الحاضرون ({len(present_names)}):
{chr(10).join(f'• {n}' for n in present_names) or 'لا يوجد'}

❌ الغائبون ({len(absent_names)}):
{chr(10).join(f'• {n}' for n in absent_names[:50]) or 'لا يوجد'}
{'...(والمزيد)' if len(absent_names) > 50 else ''}

تعليمات:
- رد بالعربية دائماً
- كن مختصراً وواضحاً
- استخدم الإيموجي للوضوح
- لو سألوا عن موظف معين ابحث في الأسماء وأجب بدقة
- لو البيانات فارغة أخبر المستخدم بمشكلة الاتصال بالشيت
"""

    response = claude.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_question}]
    )
    return response.content[0].text

# ── Telegram Handlers ─────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 أهلاً! أنا بوت الحضور والغياب الذكي 📋\n\n"
        "بقرا شيتك من Google Sheets مباشرة وبرد على أسئلتك!\n\n"
        "جرب:\n"
        "• من الغائبين النهارده؟\n"
        "• كم نسبة الحضور؟\n"
        "• هل لطفي مراد حاضر؟\n"
        "• /report — تقرير كامل\n"
        "• /refresh — تحديث البيانات"
    )

async def cmd_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_chat_action(ChatAction.TYPING)
    csv = await fetch_sheet()
    if not csv:
        await update.message.reply_text("⚠️ مش قادر أوصل للشيت، تأكد إنه Public.")
        return
    att = parse_attendance(csv)
    text = (
        f"📊 *تقرير الحضور*\n"
        f"🕐 آخر تحديث: {att['fetched_at']}\n\n"
        f"👥 الإجمالي: *{att['total']}* موظف\n"
        f"✅ الحاضرون: *{att['present']}* ({att['pct']}%)\n"
        f"❌ الغائبون: *{att['absent']}* ({100 - att['pct']}%)\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_refresh(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_chat_action(ChatAction.TYPING)
    csv = await fetch_sheet()
    if not csv:
        await update.message.reply_text("⚠️ فشل التحديث، تأكد إن الشيت Public.")
        return
    att = parse_attendance(csv)
    await update.message.reply_text(
        f"✅ تم التحديث!\n"
        f"🕐 {att['fetched_at']}\n"
        f"👥 {att['total']} موظف | ✅ {att['present']} حاضر | ❌ {att['absent']} غائب"
    )

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    question = update.message.text.strip()
    if not question:
        return

    await update.message.reply_chat_action(ChatAction.TYPING)

    # جيب البيانات الحديثة
    csv = await fetch_sheet()
    if not csv:
        await update.message.reply_text(
            "⚠️ مش قادر أقرا الشيت دلوقتي.\n"
            "تأكد إن الشيت Public وابعت أي رسالة تاني."
        )
        return

    att = parse_attendance(csv)

    # اسأل Claude
    try:
        answer = await ask_claude(question, att)
        await update.message.reply_text(answer)
    except Exception as e:
        logger.error(f"Claude error: {e}")
        await update.message.reply_text("⚠️ حصل خطأ، جرب تاني.")

# ── Main ──────────────────────────────────────────────────
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("report",  cmd_report))
    app.add_handler(CommandHandler("refresh", cmd_refresh))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("🤖 البوت شغال...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

SHEET_GID      = os.environ.get("SHEET_GID", "0")

SHEET_CSV_URL = (
    f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
    f"/export?format=csv&gid={SHEET_GID}"
)

gemini = genai.Client(api_key=GEMINI_KEY)

async def fetch_sheet() -> str:
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            r = await client.get(SHEET_CSV_URL)
            r.raise_for_status()
            return r.text
    except Exception as e:
        logger.error(f"Sheet error: {e}")
        return ""

def parse_attendance(csv_text: str) -> dict:
    lines = [l for l in csv_text.strip().splitlines() if l.strip()]
    employees = []
    for line in lines:
        cols = line.split(",")
        if not cols:
            continue
        name_cell = cols[0].strip().strip('"')
        if not name_cell or name_cell.startswith("=") or name_cell.startswith("http"):
            continue
        status_cell = cols[1].strip().strip('"') if len(cols) > 1 else ""
        present = "✔" in status_cell or status_cell.lower() in ("1","true","yes","حاضر","present")
        employees.append({"name": name_cell, "present": present})
    total   = len(employees)
    present = sum(1 for e in employees if e["present"])
    absent  = total - present
    pct     = round((present / total) * 100) if total else 0
    return {
        "total": total, "present": present, "absent": absent, "pct": pct,
        "employees": employees,
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }

async def ask_gemini(question: str, att: dict) -> str:
    present_names = [e["name"] for e in att["employees"] if e["present"]]
    absent_names  = [e["name"] for e in att["employees"] if not e["present"]]
    prompt = f"""أنت مساعد ذكي لشيت الحضور والغياب. رد دايماً بالعربي بشكل مختصر وواضح مع إيموجي.

📊 بيانات الحضور (تحديث: {att['fetched_at']}):
- الإجمالي: {att['total']} موظف
- الحاضرون: {att['present']} ({att['pct']}%)
- الغائبون: {att['absent']} ({100 - att['pct']}%)

✅ الحاضرون: {', '.join(present_names) or 'لا يوجد'}
❌ الغائبون: {', '.join(absent_names) or 'لا يوجد'}

سؤال: {question}"""
    try:
        response = gemini.models.generate_content(model="gemini-1.5-flash", contents=prompt)
        return response.text
    except Exception as e:
        logger.error(f"Gemini error: {e}")
        return "⚠️ حصل خطأ، جرب تاني."

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 أهلاً! أنا بوت الحضور والغياب الذكي 📋\n\n"
        "الأوامر:\n"
        "📊 /report — تقرير كامل\n"
        "🔄 /refresh — تحديث البيانات\n"
        "❌ /absent — قائمة الغائبين\n"
        "✅ /present — قائمة الحاضرين\n\n"
        "أو اسألني بالعربي مباشرة! 💬"
    )

async def cmd_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_chat_action(ChatAction.TYPING)
    csv = await fetch_sheet()
    if not csv:
        await update.message.reply_text("⚠️ مش قادر أوصل للشيت، تأكد إنه Public.")
        return
    att = parse_attendance(csv)
    await update.message.reply_text(
        f"📊 *تقرير الحضور*\n🕐 {att['fetched_at']}\n\n"
        f"👥 الإجمالي: *{att['total']}* موظف\n"
        f"✅ الحاضرون: *{att['present']}* ({att['pct']}%)\n"
        f"❌ الغائبون: *{att['absent']}* ({100 - att['pct']}%)",
        parse_mode="Markdown"
    )

async def cmd_refresh(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_chat_action(ChatAction.TYPING)
    csv = await fetch_sheet()
    if not csv:
        await update.message.reply_text("⚠️ فشل التحديث.")
        return
    att = parse_attendance(csv)
    await update.message.reply_text(
        f"✅ *تم التحديث!*\n🕐 {att['fetched_at']}\n"
        f"👥 {att['total']} موظف | ✅ {att['present']} | ❌ {att['absent']}",
        parse_mode="Markdown"
    )

async def cmd_absent(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_chat_action(ChatAction.TYPING)
    csv = await fetch_sheet()
    if not csv:
        await update.message.reply_text("⚠️ مش قادر أوصل للشيت.")
        return
    att = parse_attendance(csv)
    absent = [e["name"] for e in att["employees"] if not e["present"]]
    if not absent:
        await update.message.reply_text("🎉 مفيش غائبين النهارده!")
        return
    text = f"❌ *الغائبون ({len(absent)}):*\n\n" + "\n".join(f"• {n}" for n in absent[:50])
    if len(absent) > 50:
        text += f"\n\n_...و {len(absent)-50} آخرين_"
    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_present(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_chat_action(ChatAction.TYPING)
    csv = await fetch_sheet()
    if not csv:
        await update.message.reply_text("⚠️ مش قادر أوصل للشيت.")
        return
    att = parse_attendance(csv)
    present = [e["name"] for e in att["employees"] if e["present"]]
    if not present:
        await update.message.reply_text("😔 مفيش حاضرين!")
        return
    text = f"✅ *الحاضرون ({len(present)}):*\n\n" + "\n".join(f"• {n}" for n in present)
    await update.message.reply_text(text, parse_mode="Markdown")

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    question = update.message.text.strip()
    if not question:
        return
    await update.message.reply_chat_action(ChatAction.TYPING)
    csv = await fetch_sheet()
    if not csv:
        await update.message.reply_text("⚠️ مش قادر أقرا الشيت، تأكد إنه Public.")
        return
    att = parse_attendance(csv)
    answer = await ask_gemini(question, att)
    await update.message.reply_text(answer)

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("report",  cmd_report))
    app.add_handler(CommandHandler("refresh", cmd_refresh))
    app.add_handler(CommandHandler("absent",  cmd_absent))
    app.add_handler(CommandHandler("present", cmd_present))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("🤖 البوت شغال...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
