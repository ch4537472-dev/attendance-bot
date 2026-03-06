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

SHEETS = {
    "employees":  "0",
    "salaries":   "1192177959",
    "attendance": "962128039",
    "leaves":     "1743768834",
    "managers":   "1729097761",
}

gemini = genai.Client(api_key=GEMINI_KEY)

async def fetch_sheet(gid: str) -> str:
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={gid}"
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            r = await client.get(url)
            r.raise_for_status()
            return r.text
    except Exception as e:
        logger.error(f"Sheet error (gid={gid}): {e}")
        return ""

async def fetch_all_sheets() -> dict:
    data = {}
    for name, gid in SHEETS.items():
        csv = await fetch_sheet(gid)
        data[name] = csv
    return data

def csv_summary(csv_text: str, max_rows: int = 30) -> str:
    if not csv_text:
        return "لا توجد بيانات"
    lines = [l for l in csv_text.strip().splitlines() if l.strip()]
    return "\n".join(lines[:max_rows])

async def ask_gemini(question: str, all_data: dict) -> str:
    sheets_content = ""
    for name, csv in all_data.items():
        sheets_content += f"\n\n=== تبويب {name} ===\n{csv_summary(csv)}"

    prompt = f"""أنت مساعد ذكي لشيت Excel. رد دايماً بالعربي بشكل مختصر وواضح مع إيموجي.

البيانات (آخر تحديث: {datetime.now().strftime('%Y-%m-%d %H:%M')}):
{sheets_content}

سؤال المستخدم: {question}"""

    try:
        response = gemini.models.generate_content(
            model="gemini-1.5-flash" ,
            contents=prompt
        )
        return response.text
   except Exception as e:
    logger.error(f"Gemini error: {e}")
    return "⚠️ حصل خطأ، جرب تاني."

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 أهلاً! أنا مساعدك الذكي للشيت 📋\n\n"
        "عندي بيانات من 5 تبويبات:\n"
        "👥 employees — الموظفين\n"
        "💰 salaries — المرتبات\n"
        "📅 attendance — الحضور\n"
        "🏖 leaves — الإجازات\n"
        "👔 managers — المديرين\n\n"
        "الأوامر:\n"
        "📊 /report — تقرير شامل\n"
        "👥 /employees — بيانات الموظفين\n"
        "💰 /salaries — المرتبات\n"
        "📅 /attendance — الحضور والغياب\n"
        "🏖 /leaves — الإجازات\n"
        "👔 /managers — المديرين\n\n"
        "أو اسألني أي سؤال بالعربي! 💬"
    )

async def cmd_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_chat_action(ChatAction.TYPING)
    all_data = await fetch_all_sheets()
    answer = await ask_gemini("اعمل تقرير شامل ومختصر عن كل التبويبات", all_data)
    await update.message.reply_text(
        f"📊 *تقرير شامل*\n🕐 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n{answer}",
        parse_mode="Markdown"
    )

async def cmd_employees(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_chat_action(ChatAction.TYPING)
    all_data = await fetch_all_sheets()
    answer = await ask_gemini("اعرض ملخص بيانات الموظفين", all_data)
    await update.message.reply_text(f"👥 *الموظفون*\n\n{answer}", parse_mode="Markdown")

async def cmd_salaries(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_chat_action(ChatAction.TYPING)
    all_data = await fetch_all_sheets()
    answer = await ask_gemini("اعرض ملخص المرتبات", all_data)
    await update.message.reply_text(f"💰 *المرتبات*\n\n{answer}", parse_mode="Markdown")

async def cmd_attendance(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_chat_action(ChatAction.TYPING)
    all_data = await fetch_all_sheets()
    answer = await ask_gemini("اعرض ملخص الحضور والغياب", all_data)
    await update.message.reply_text(f"📅 *الحضور والغياب*\n\n{answer}", parse_mode="Markdown")

async def cmd_leaves(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_chat_action(ChatAction.TYPING)
    all_data = await fetch_all_sheets()
    answer = await ask_gemini("اعرض ملخص الإجازات", all_data)
    await update.message.reply_text(f"🏖 *الإجازات*\n\n{answer}", parse_mode="Markdown")

async def cmd_managers(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_chat_action(ChatAction.TYPING)
    all_data = await fetch_all_sheets()
    answer = await ask_gemini("اعرض بيانات المديرين", all_data)
    await update.message.reply_text(f"👔 *المديرون*\n\n{answer}", parse_mode="Markdown")

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    question = update.message.text.strip()
    if not question:
        return
    await update.message.reply_chat_action(ChatAction.TYPING)
    all_data = await fetch_all_sheets()
    answer = await ask_gemini(question, all_data)
    await update.message.reply_text(answer)

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start",      cmd_start))
    app.add_handler(CommandHandler("report",     cmd_report))
    app.add_handler(CommandHandler("employees",  cmd_employees))
    app.add_handler(CommandHandler("salaries",   cmd_salaries))
    app.add_handler(CommandHandler("attendance", cmd_attendance))
    app.add_handler(CommandHandler("leaves",     cmd_leaves))
    app.add_handler(CommandHandler("managers",   cmd_managers))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("🤖 البوت شغال...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
