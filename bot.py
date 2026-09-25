import sys
import re
import os
from datetime import datetime, timedelta
from io import BytesIO
from PIL import Image
import pytesseract

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

import database as db
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

# ករណី Windows ត្រូវបើក comment ខាងក្រោមដើម្បីបញ្ជាក់ path ទៅ tesseract.exe
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# ----------------- OCR ស្រង់ទឹកប្រាក់ពីរូបភាព -----------------
def extract_amount_from_image(image_bytes):
    try:
        img = Image.open(BytesIO(image_bytes))
        text = pytesseract.image_to_string(img)
        
        # ស្វែងរកលេខទឹកប្រាក់ (ឧ. $120.50, 50,000 KHR, 25.00 USD)
        usd_pattern = r"\$\s?([0-9]+(?:,[0-9]{3})*(?:\.[0-9]{1,2})?)"
        khr_pattern = r"([0-9]+(?:,[0-9]{3})*)\s?(?:KHR|៛)"
        
        usd_match = re.search(usd_pattern, text)
        if usd_match:
            amount_str = usd_match.group(1).replace(",", "")
            return float(amount_str), "USD"
            
        khr_match = re.search(khr_pattern, text, re.IGNORECASE)
        if khr_match:
            amount_str = khr_match.group(1).replace(",", "")
            return float(amount_str), "KHR"
            
        return None, text
    except Exception as e:
        return None, str(e)

# ----------------- Command Handlers -----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.register_user(user.id, user.username, user.full_name)
    
    welcome_msg = (
        f"ជំរាបសួរ {user.full_name}!\n"
        "សូមស្វាគមន៍មកកាន់ប្រព័ន្ធគ្រប់គ្រងហិរញ្ញវត្ថុឆ្លាតវៃ។\n\n"
        " របៀបកត់ត្រាដោយដៃ៖\n"
        "• ចំណូល: `+ ចំនួន ផ្នែក ការពិពណ៌នា`\n"
        "  ឧទាហរណ៍: `+ 500 ប្រាក់ខែ ទទួលប្រាក់ខែដើមខែ`\n"
        "• ចំណាយ: `- ចំនួន ផ្នែក ការពិពណ៌នា`\n"
        "  ឧទាហរណ៍: `- 15 ម្ហូបអាហារ ញ៉ាំបាយថ្ងៃត្រង់`\n\n"
        " របៀបកត់ត្រាតាមវិក្កយបត្រ៖ ផ្ញើរូបភាពវិក្កយបត្រធនាគារចូលទីនេះ\n"
        " របាយការណ៍៖ វាយ /report\n"
        " កែប្រែ/លុប៖ វាយ /edit [ID] ឬ /delete [ID]"
    )
    await update.message.reply_text(welcome_msg, parse_mode="Markdown")

# ----------------- កត់ត្រាដោយដៃ (+ / -) -----------------
async def handle_text_record(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.effective_user.id
    
    if not db.is_registered(user_id):
        await update.message.reply_text("សូមចុះឈ្មោះជាមុនដោយវាយ /start")
        return

    # ទម្រង់: + 100 Category Description ឬ - 100 Category Description
    match = re.match(r"^([+-])\s*([0-9]+(?:\.[0-9]+)?)\s+([^\s]+)(?:\s+(.*))?$", text)
    if match:
        sign, amount_str, category, desc = match.groups()
        amount = float(amount_str)
        trans_type = "income" if sign == "+" else "expense"
        desc = desc if desc else "គ្មានកំណត់សម្គាល់"
        
        trans_id = db.add_transaction(user_id, trans_type, amount, category, desc)
        emoji = " ទទួល" if trans_type == "income" else " ចំណាយ"
        
        await update.message.reply_text(
            f"✅ កត់ត្រាជោគជ័យ! (ID: {trans_id})\n"
            f"• ប្រភេទ: {emoji}\n"
            f"• ទឹកប្រាក់: ${amount:,.2f}\n"
            f"• ផ្នែក: {category}\n"
            f"• បរិយាយ: {desc}"
        )

# ----------------- អានរូបភាពវិក្កយបត្រ -----------------
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not db.is_registered(user_id):
        await update.message.reply_text("សូមចុះឈ្មោះជាមុនដោយវាយ /start")
        return

    photo = await update.message.photo[-1].get_file()
    image_bytes = await photo.download_as_bytearray()
    
    amount, currency = extract_amount_from_image(image_bytes)
    
    if amount:
        # កត់ត្រាជាចំណូល ឬចំណាយដោយស្វ័យប្រវត្តិ (លំនាំដើម: ធនាគារ)
        trans_id = db.add_transaction(user_id, "expense", amount, "ធនាគារ", f"ស្កេនពីវិក្កយបត្រ ({currency})")
        await update.message.reply_text(
            f" ស្កេនជោគជ័យ! បានកត់ត្រាចូលបញ្ជី៖\n"
            f"• លេខសម្គាល់: ID {trans_id}\n"
            f"• ទឹកប្រាក់រកឃើញ: {amount:,.2f} {currency}\n"
            f"• ផ្នែក: ធនាគារ\n\n"
            f"(ប្រសិនបើជាចំណូល ឬចង់ប្ដូរប្រភេទ សូមប្រើ: `/edit {trans_id} [amount] [category] [desc]`)"
        )
    else:
        await update.message.reply_text(" មិនអាចទាញយកទឹកប្រាក់ពីរូបភាពបានទេ។ សូមបញ្ចូលដោយដៃតាមទម្រង់: `- [ចំនួន] [ផ្នែក] [បរិយាយ]`")

# ----------------- របាយការណ៍បែងចែកពេលវេលា -----------------
async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(" ប្រចាំថ្ងៃ", callback_data="rep_daily"),
         InlineKeyboardButton(" ប្រចាំសប្ដាហ៍", callback_data="rep_weekly")],
        [InlineKeyboardButton(" ប្រចាំខែ", callback_data="rep_monthly"),
         InlineKeyboardButton(" ប្រចាំត្រីមាស", callback_data="rep_quarterly")],
        [InlineKeyboardButton(" ប្រចាំឆមាស", callback_data="rep_semiannual"),
         InlineKeyboardButton(" ប្រចាំឆ្នាំ", callback_data="rep_yearly")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("សូមជ្រើសរើសចន្លោះពេលដើម្បីមើលរបាយការណ៍៖", reply_markup=reply_markup)

async def report_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    now = datetime.now()
    
    if data == "rep_daily":
        start_date = end_date = now.strftime("%Y-%m-%d")
        title = "ប្រចាំថ្ងៃ"
    elif data == "rep_weekly":
        start_date = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        end_date = now.strftime("%Y-%m-%d")
        title = "ប្រចាំសប្ដាហ៍"
    elif data == "rep_monthly":
        start_date = now.strftime("%Y-%m-01")
        end_date = now.strftime("%Y-%m-%d")
        title = "ប្រចាំខែនេះ"
    elif data == "rep_quarterly":
        start_date = (now - timedelta(days=90)).strftime("%Y-%m-%d")
        end_date = now.strftime("%Y-%m-%d")
        title = "ប្រចាំត្រីមាស (៩០ ថ្ងៃចុងក្រោយ)"
    elif data == "rep_semiannual":
        start_date = (now - timedelta(days=180)).strftime("%Y-%m-%d")
        end_date = now.strftime("%Y-%m-%d")
        title = "ប្រចាំឆមាស (១៨០ ថ្ងៃចុងក្រោយ)"
    elif data == "rep_yearly":
        start_date = now.strftime("%Y-01-01")
        end_date = now.strftime("%Y-%m-%d")
        title = "ប្រចាំឆ្នាំនេះ"
    else:
        return

    records = db.get_report(user_id, start_date, end_date)
    
    total_inc = 0.0
    total_exp = 0.0
    breakdown_text = ""
    
    for r_type, cat, amt, count in records:
        if r_type == "income":
            total_inc += amt
            breakdown_text += f"• [ចំណូល] {cat}: +${amt:,.2f} ({count} ដង)\n"
        else:
            total_exp += amt
            breakdown_text += f"• [ចំណាយ] {cat}: -${amt:,.2f} ({count} ដង)\n"
            
    balance = total_inc - total_exp
    body_text = breakdown_text if breakdown_text else "មិនមានទិន្នន័យឡើយ\n"
    
    msg = (
        f" **របាយការណ៍ {title}**\n"
        f"ចន្លោះ: `{start_date}` ដល់ `{end_date}`\n"
        f"-----------------------------\n"
        f"{body_text}"
        f"-----------------------------\n"
        f" សរុបចំណូល: +${total_inc:,.2f}\n"
        f" សរុបចំណាយ: -${total_exp:,.2f}\n"
        f" សមតុល្យសល់: **${balance:,.2f}**"
    )
    await query.edit_message_text(msg, parse_mode="Markdown")

# ----------------- ធ្វើបច្ចុប្បន្នភាព និងលុប (Update/Edit) -----------------
async def edit_record(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ឧទាហរណ៍: /edit 1 25.50 ម្ហូប ញ៉ាំបាយ
    user_id = update.effective_user.id
    args = context.args
    
    if len(args) < 3:
        await update.message.reply_text("ទម្រង់ខុស! គំរូ: `/edit [ID] [ចំនួនទឹកប្រាក់] [ផ្នែក] [បរិយាយ]`", parse_mode="Markdown")
        return
        
    try:
        trans_id = int(args[0])
        amount = float(args[1])
        category = args[2]
        desc = " ".join(args[3:]) if len(args) > 3 else "កែប្រែថ្មី"
        
        ok = db.update_transaction(trans_id, user_id, amount=amount, category=category, description=desc)
        if ok:
            await update.message.reply_text(f"✅ បានធ្វើបច្ចុប្បន្នភាពប្រតិបត្តិការ ID {trans_id} រួចរាល់!")
        else:
            await update.message.reply_text("❌ រកមិនឃើញ ID ឬអ្នកគ្មានសិទ្ធិកែប្រែប្រតិបត្តិការនេះឡើយ។")
    except ValueError:
        await update.message.reply_text("❌ ទឹកប្រាក់ ឬ ID ត្រូវតែជាលេខ។")

async def delete_record(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ឧទាហរណ៍: /delete 1
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("គំរូ: `/delete [ID]`", parse_mode="Markdown")
        return
    try:
        trans_id = int(context.args[0])
        ok = db.delete_transaction(trans_id, user_id)
        if ok:
            await update.message.reply_text(f"🗑 បានលុបប្រតិបត្តិការ ID {trans_id} ដោយជោគជ័យ!")
        else:
            await update.message.reply_text("❌ រកមិនឃើញ ID ឬអ្នកគ្មានសិទ្ធិលុបឡើយ។")
    except ValueError:
        await update.message.reply_text("❌ ID ត្រូវតែជាលេខ។")

# ----------------- Health Check Server (សម្រាប់ Render Web Service) -----------------
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

    def log_message(self, format, *args):
        pass

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    try:
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        server.serve_forever()
    except Exception as e:
        print(f"Health server error: {e}")

# ----------------- Main App -----------------
def main():
    db.init_db()
    
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN":
        print("Error: សូមបញ្ចូល Telegram Bot Token របស់អ្នកនៅក្នុង .env ឬ Environment Variable ជាមុនសិន។")
        return

    # Start health check server if running on cloud platforms (Render / Railway)
    if "PORT" in os.environ:
        threading.Thread(target=run_health_server, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("report", report_command))
    app.add_handler(CommandHandler("edit", edit_record))
    app.add_handler(CommandHandler("delete", delete_record))
    
    app.add_handler(CallbackQueryHandler(report_callback, pattern="^rep_"))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_record))
    
    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
