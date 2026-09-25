import sys
import re
import os
from datetime import datetime, timedelta
from io import BytesIO
from PIL import Image
import pytesseract
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# កំណត់ Font គាំទ្រភាសាខ្មែរសម្រាប់ Matplotlib
khmer_fonts = ['Noto Sans Khmer', 'Khmer OS Content', 'Khmer OS Siemreap', 'Khmer UI', 'Leelawadee UI', 'Nirmala UI', 'DejaVu Sans']
plt.rcParams['font.sans-serif'] = khmer_fonts + plt.rcParams.get('font.sans-serif', [])
plt.rcParams['axes.unicode_minus'] = False

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
        " របាយការណ៍សង្ខេប៖ វាយ /report\n"
        " ក្រាហ្វិក (Chart)៖ វាយ /chart\n"
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

# ----------------- មុខងារគណនាកាលបរិច្ឆេទ & បង្កើត Chart -----------------
def get_date_range_and_title(data_key):
    now = datetime.now()
    if data_key == "rep_daily":
        return now.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d"), "ប្រចាំថ្ងៃ"
    elif data_key == "rep_weekly":
        return (now - timedelta(days=7)).strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d"), "ប្រចាំសប្ដាហ៍"
    elif data_key == "rep_monthly":
        return now.strftime("%Y-%m-01"), now.strftime("%Y-%m-%d"), "ប្រចាំខែនេះ"
    elif data_key == "rep_quarterly":
        return (now - timedelta(days=90)).strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d"), "ប្រចាំត្រីមាស (៩០ ថ្ងៃ)"
    elif data_key == "rep_semiannual":
        return (now - timedelta(days=180)).strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d"), "ប្រចាំឆមាស (១៨០ ថ្ងៃ)"
    elif data_key == "rep_yearly":
        return now.strftime("%Y-01-01"), now.strftime("%Y-%m-%d"), "ប្រចាំឆ្នាំនេះ"
    return None, None, None

def generate_finance_chart(records, title, start_date, end_date):
    if not records:
        return None

    income_by_cat = {}
    expense_by_cat = {}
    total_income = 0.0
    total_expense = 0.0

    for r_type, cat, amt, count in records:
        if r_type == 'income':
            income_by_cat[cat] = income_by_cat.get(cat, 0.0) + amt
            total_income += amt
        else:
            expense_by_cat[cat] = expense_by_cat.get(cat, 0.0) + amt
            total_expense += amt

    if total_income == 0 and total_expense == 0:
        return None

    # បង្កើត Figure រចនាប័ទ្ម Modern Dark Theme
    fig = plt.figure(figsize=(10, 5), dpi=150)
    fig.patch.set_facecolor('#1E1E2E')

    ax1 = fig.add_subplot(1, 2, 1)
    ax2 = fig.add_subplot(1, 2, 2)

    # --- ១. Bar Chart: ចំណូល vs ចំណាយ ---
    categories = ['ចំណូល (Income)', 'ចំណាយ (Expense)']
    amounts = [total_income, total_expense]
    colors = ['#2ECC71', '#E74C3C']

    bars = ax1.bar(categories, amounts, color=colors, width=0.45, edgecolor='#FFFFFF', linewidth=0.5)
    ax1.set_facecolor('#2A2B3D')
    ax1.set_title('ប្រៀបធៀបចំណូល vs ចំណាយ', color='#FFFFFF', fontsize=12, fontweight='bold', pad=12)
    ax1.tick_params(colors='#D0D0D0', labelsize=10)
    ax1.spines['bottom'].set_color('#555566')
    ax1.spines['left'].set_color('#555566')
    ax1.spines['top'].set_visible(False)
    ax1.spines['right'].set_visible(False)
    ax1.yaxis.grid(True, linestyle='--', alpha=0.3, color='#888888')

    for bar in bars:
        height = bar.get_height()
        ax1.annotate(f'${height:,.2f}',
                     xy=(bar.get_x() + bar.get_width() / 2, height),
                     xytext=(0, 4),
                     textcoords='offset points',
                     ha='center', va='bottom',
                     color='#FFFFFF', fontsize=10, fontweight='bold')

    # --- ២. Donut Chart: ចំណាត់ថ្នាក់ចំណាយ ឬចំណូល ---
    breakdown = expense_by_cat if expense_by_cat else income_by_cat
    breakdown_type = 'ចំណាត់ថ្នាក់ចំណាយ' if expense_by_cat else 'ចំណាត់ថ្នាក់ចំណូល'

    ax2.set_facecolor('#1E1E2E')
    ax2.set_title(breakdown_type, color='#FFFFFF', fontsize=12, fontweight='bold', pad=12)

    labels = list(breakdown.keys())
    values = list(breakdown.values())
    donut_colors = ['#FF6B6B', '#4ECDC4', '#FFE66D', '#1A535C', '#F7B801', '#9B5DE5', '#00BBF9', '#00F5D4']
    if len(labels) > len(donut_colors):
        donut_colors = donut_colors * ((len(labels) // len(donut_colors)) + 1)

    wedges, texts, autotexts = ax2.pie(
        values,
        labels=labels,
        autopct='%1.1f%%',
        startangle=140,
        colors=donut_colors[:len(labels)],
        wedgeprops=dict(width=0.4, edgecolor='#1E1E2E', linewidth=2),
        textprops=dict(color='#EAEAEA', fontsize=9),
        pctdistance=0.75
    )
    for autotext in autotexts:
        autotext.set_color('#FFFFFF')
        autotext.set_fontweight('bold')
        autotext.set_fontsize(8)

    plt.suptitle(f'របាយការណ៍ហិរញ្ញវត្ថុ {title} ({start_date} ដល់ {end_date})',
                 color='#F1F2F6', fontsize=13, fontweight='bold', y=0.98)

    plt.tight_layout(rect=[0, 0.03, 1, 0.95])

    buf = BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    return buf

# ----------------- របាយការណ៍បែងចែកពេលវេលា -----------------
async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📅 ប្រចាំថ្ងៃ", callback_data="rep_daily"),
         InlineKeyboardButton("📅 ប្រចាំសប្ដាហ៍", callback_data="rep_weekly")],
        [InlineKeyboardButton("📅 ប្រចាំខែ", callback_data="rep_monthly"),
         InlineKeyboardButton("📅 ប្រចាំត្រីមាស", callback_data="rep_quarterly")],
        [InlineKeyboardButton("📅 ប្រចាំឆមាស", callback_data="rep_semiannual"),
         InlineKeyboardButton("📅 ប្រចាំឆ្នាំ", callback_data="rep_yearly")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("សូមជ្រើសរើសចន្លោះពេលដើម្បីមើលរបាយការណ៍៖", reply_markup=reply_markup)

async def report_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    start_date, end_date, title = get_date_range_and_title(data)
    if not start_date:
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
    
    # បន្ថែមប៊ូតុងមើល Chart ប្រសិនបើមានទិន្នន័យ
    keyboard = []
    if records:
        keyboard.append([InlineKeyboardButton("📊 បង្ហាញក្រាហ្វិក (Chart)", callback_data=f"chart_{data}")])
    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    
    await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=reply_markup)

# ----------------- បង្ហាញ Chart (ក្រាហ្វិក) -----------------
async def chart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📊 ប្រចាំថ្ងៃ", callback_data="chart_rep_daily"),
         InlineKeyboardButton("📊 ប្រចាំសប្ដាហ៍", callback_data="chart_rep_weekly")],
        [InlineKeyboardButton("📊 ប្រចាំខែ", callback_data="chart_rep_monthly"),
         InlineKeyboardButton("📊 ប្រចាំត្រីមាស", callback_data="chart_rep_quarterly")],
        [InlineKeyboardButton("📊 ប្រចាំឆមាស", callback_data="chart_rep_semiannual"),
         InlineKeyboardButton("📊 ប្រចាំឆ្នាំ", callback_data="chart_rep_yearly")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📊 សូមជ្រើសរើសចន្លោះពេលដើម្បីបង្កើត Chart ក្រាហ្វិក៖", reply_markup=reply_markup)

async def chart_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data.replace("chart_", "")
    user_id = query.from_user.id

    start_date, end_date, title = get_date_range_and_title(data)
    if not start_date:
        return

    records = db.get_report(user_id, start_date, end_date)
    chart_buf = generate_finance_chart(records, title, start_date, end_date)

    if chart_buf:
        caption = f"📊 **ក្រាហ្វិករបាយការណ៍ហិរញ្ញវត្ថុ {title}**\nចន្លោះ: `{start_date}` ដល់ `{end_date}`"
        await query.message.reply_photo(photo=chart_buf, caption=caption, parse_mode="Markdown")
    else:
        await query.message.reply_text(f"⚠️ មិនមានទិន្នន័យសម្រាប់បង្កើតក្រាហ្វិក {title} (`{start_date}` ដល់ `{end_date}`) ឡើយ។")

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
    app.add_handler(CommandHandler("chart", chart_command))
    app.add_handler(CommandHandler("edit", edit_record))
    app.add_handler(CommandHandler("delete", delete_record))
    
    app.add_handler(CallbackQueryHandler(chart_callback, pattern="^chart_"))
    app.add_handler(CallbackQueryHandler(report_callback, pattern="^rep_"))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_record))
    
    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
