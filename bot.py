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
SHEET_ID       = os.environ["SHEET_ID"]
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
