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

# ករណី Windows ត្រូវបើក comment ខាងក្រោមដើម្បីបញ្ជាក់ path ទៅ tesseract.exe (បើចាំបាច់)
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# ----------------- អានបង្កាន់ដៃធនាគារ (Bank Payslip / Transaction Slip) -----------------
def extract_bank_slip_info(image_bytes):
    """
    អាន Bank Payslip / Transaction Slip (បង្កាន់ដៃធនាគារ ABA, ACLEDA, Wing, Canadia, Bakong...)
    ទាញយក: Bank Name, Transaction Type (income/expense), Amount, Currency (USD/KHR), Description
    """
    try:
        img = Image.open(BytesIO(image_bytes))
        if img.mode != "RGB":
            img = img.convert("RGB")
            
        text = pytesseract.image_to_string(img)
        
        # ១. ស្វែងរកឈ្មោះធនាគារ (Bank Name)
        bank_name = "ធនាគារ"
        if re.search(r"\baba\b|advanced bank", text, re.I):
            bank_name = "ABA Bank"
        elif re.search(r"\bacleda\b|toanchet|អេស៊ីលីដា", text, re.I):
            bank_name = "ACLEDA Bank"
        elif re.search(r"\bwing\b|wingmoney", text, re.I):
            bank_name = "Wing Bank"
        elif re.search(r"\bcanadia\b|កាណាឌីយ៉ា", text, re.I):
            bank_name = "Canadia Bank"
        elif re.search(r"bakong|khqr|បាគង", text, re.I):
            bank_name = "Bakong / KHQR"
        elif re.search(r"truemoney", text, re.I):
            bank_name = "TrueMoney"
        elif re.search(r"sathapana", text, re.I):
            bank_name = "Sathapana Bank"
        elif re.search(r"chip mong", text, re.I):
            bank_name = "Chip Mong Bank"

        # ២. ស្វែងរកប្រភេទប្រតិបត្តិការ (Income vs Expense)
        trans_type = "expense"
        has_income_keywords = re.search(r"received from|from account|sender:|ដាក់ប្រាក់|ទទួលពី|cash in|credit", text, re.I)
        has_expense_keywords = re.search(r"paid to|transfer to|to account|merchant|អ្នកទទួល|payment to|debit", text, re.I)
        if has_income_keywords and not has_expense_keywords:
            trans_type = "income"

        # ៣. ស្វែងរកចំនួនទឹកប្រាក់ និងរូបិយប័ណ្ណ ($ ឬ ៛)
        amount = None
        currency = "USD"

        # ស្វែងរក KHR (៛)
        khr_match = re.search(r"([0-9]{1,3}(?:,[0-9]{3})*|[0-9]+(?:\.[0-9]+)?)\s*(?:KHR|៛|Riel|រៀល)", text, re.I)
        if not khr_match:
            khr_match = re.search(r"(?:KHR|៛)\s*([0-9]{1,3}(?:,[0-9]{3})*|[0-9]+(?:\.[0-9]+)?)", text, re.I)

        # ស្វែងរក USD ($)
        usd_match = re.search(r"\$\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)", text)
        if not usd_match:
            usd_match = re.search(r"([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)\s*(?:USD|\$)", text, re.I)

        if khr_match and not usd_match:
            amount = float(khr_match.group(1).replace(",", ""))
            currency = "KHR"
        elif usd_match:
            amount = float(usd_match.group(1).replace(",", ""))
            currency = "USD"
        elif khr_match:
            amount = float(khr_match.group(1).replace(",", ""))
            currency = "KHR"
        else:
            # Fallback: រកមើលលេខទឹកប្រាក់ក្បែរពាក្យ Amount ឬ Total
            amt_fallback = re.search(r"(?:amount|total|ទឹកប្រាក់|ចំនួន)\s*[:\-]?\s*([0-9,.]+)", text, re.I)
            if amt_fallback:
                raw_amt = float(amt_fallback.group(1).replace(",", ""))
                if raw_amt >= 500 and "." not in amt_fallback.group(1):
                    amount = raw_amt
                    currency = "KHR"
                else:
                    amount = raw_amt
                    currency = "USD"

        # ៤. ស្រង់អ្នកទទួល (Beneficiary) ឬ Remark
        desc = ""
        to_match = re.search(r"(?:to account|paid to|transfer to|to|merchant|អ្នកទទួល)\s*[:\-]?\s*([^\n\r]+)", text, re.I)
        if to_match:
            desc = to_match.group(1).strip()
        
        remark_match = re.search(r"(?:remark|note|description|purpose|កំណត់សម្គាល់|មូលហេតុ)\s*[:\-]?\s*([^\n\r]+)", text, re.I)
        if remark_match:
            rem = remark_match.group(1).strip()
            desc = f"{desc} ({rem})" if desc else rem

        if not desc:
            desc = f"បង្កាន់ដៃ {bank_name}"

        return bank_name, trans_type, amount, currency, desc, text
    except Exception as e:
        return "ធនាគារ", "expense", None, "USD", str(e), str(e)

# ----------------- ជំនួយការ parse កាលបរិច្ឆេទ -----------------
def parse_date_argument(date_str):
    if not date_str:
        return None
    date_str = date_str.strip()
    m1 = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$", date_str)
    if m1:
        y, m, d = m1.groups()
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    m2 = re.match(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$", date_str)
    if m2:
        d, m, y = m2.groups()
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    return None

def get_date_range_and_title(data_key):
    now = datetime.now()
    if data_key.startswith("custom_"):
        parts = data_key.replace("custom_", "").split("_")
        if len(parts) >= 2:
            return parts[0], parts[1], f"កំណត់ថ្ងៃ ({parts[0]} ដល់ {parts[1]})"
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

# ----------------- Command Handlers -----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.register_user(user.id, user.username, user.full_name)
    
    welcome_msg = (
        f"ជំរាបសួរ {user.full_name}!\n"
        "សូមស្វាគមន៍មកកាន់ប្រព័ន្ធគ្រប់គ្រងហិរញ្ញវត្ថុឆ្លាតវៃ (បែងចែក $ និង ៛)។\n\n"
        "💵 **របៀបកត់ត្រាដោយដៃ៖**\n"
        "• ដុល្លារ ($)៖\n"
        "  `+ 500$ ប្រាក់ខែ ទទួលប្រាក់ខែ` (ឬ `+ 500 ប្រាក់ខែ`)\n"
        "  `- 15$ ម្ហូប បាយថ្ងៃត្រង់`\n"
        "• រៀល (៛)៖\n"
        "  `+ 2000000៛ ប្រាក់ខែ ទទួលប្រាក់ខែ`\n"
        "  `- 60000៛ ម្ហូប បាយថ្ងៃត្រង់`\n\n"
        "🧾 **ស្កេនបង្កាន់ដៃធនាគារ (Bank Payslip)៖**\n"
        "• ផ្ញើរូបភាពបង្កាន់ដៃ (ABA, ACLEDA, Wing, Canadia, Bakong...) ចូលទីនេះ ប្រព័ន្ធនឹងស្រង់ទឹកប្រាក់ ធនាគារ និងរូបិយប័ណ្ណ ($/៛) ដោយស្វ័យប្រវត្តិ!\n\n"
        "📊 **របាយការណ៍ & ក្រាហ្វិក៖**\n"
        "• /report : របាយការណ៍ទូទៅ (ឬ `/report 2026-09-01 2026-09-25`)\n"
        "• /chart : ក្រាហ្វិកវិភាគ (ឬ `/chart 2026-09-01 2026-09-25`)\n"
        "• /bank : បូកសរុបបង្កាន់ដៃគ្រប់ធនាគារ (ឬ `/bank 2026-09-01 2026-09-25`)\n"
        "• /edit [ID] [ចំនួន$ ឬ ៛] [ផ្នែក] [បរិយាយ] : កែប្រែទិន្នន័យ\n"
        "• /delete [ID] : លុបទិន្នន័យ"
    )
    await update.message.reply_text(welcome_msg, parse_mode="Markdown")

# ----------------- កត់ត្រាដោយដៃ (+ / -) -----------------
async def handle_text_record(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.effective_user.id
    
    if not db.is_registered(user_id):
        await update.message.reply_text("សូមចុះឈ្មោះជាមុនដោយវាយ /start")
        return

    # ទម្រង់: + 100$ Category Description ឬ - 40000៛ Category Description
    match = re.match(r"^([+-])\s*(\$|៛|USD|KHR|R)?\s*([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)\s*(\$|៛|USD|KHR|R)?\s+([^\s]+)(?:\s+(.*))?$", text, re.I)
    if match:
        sign, cur_pre, amt_str, cur_post, category, desc = match.groups()
        amount = float(amt_str.replace(",", ""))
        trans_type = "income" if sign == "+" else "expense"
        
        cur_tag = (cur_pre or cur_post or "").upper()
        if cur_tag in ("៛", "KHR", "R"):
            currency = "KHR"
        else:
            currency = "USD"
            
        desc = desc.strip() if desc else "គ្មានកំណត់សម្គាល់"
        
        trans_id = db.add_transaction(user_id, trans_type, amount, category, desc, currency=currency)
        emoji = " ទទួល (ចំណូល)" if trans_type == "income" else " ចំណាយ"
        cur_symbol = "$" if currency == "USD" else "៛"
        amt_display = f"${amount:,.2f}" if currency == "USD" else f"{amount:,.0f} ៛"
        
        await update.message.reply_text(
            f"✅ **កត់ត្រាជោគជ័យ!** (ID: {trans_id})\n"
            f"• ប្រភេទ: {emoji}\n"
            f"• រូបិយប័ណ្ណ: {currency} ({cur_symbol})\n"
            f"• ទឹកប្រាក់: **{amt_display}**\n"
            f"• ផ្នែក: {category}\n"
            f"• បរិយាយ: {desc}"
        )

# ----------------- អានរូបភាពវិក្កយបត្រធនាគារ -----------------
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not db.is_registered(user_id):
        await update.message.reply_text("សូមចុះឈ្មោះជាមុនដោយវាយ /start")
        return

    photo = await update.message.photo[-1].get_file()
    image_bytes = await photo.download_as_bytearray()
    
    bank_name, trans_type, amount, currency, desc, raw_text = extract_bank_slip_info(image_bytes)
    
    if amount:
        desc_tagged = f"[បង្កាន់ដៃ] {desc}" if not desc.startswith("[បង្កាន់ដៃ]") else desc
        trans_id = db.add_transaction(user_id, trans_type, amount, bank_name, desc_tagged, currency=currency)
        type_emoji = " ទទួលប្រាក់ (ចំណូល)" if trans_type == "income" else " ទូទាត់/ផ្ទេរប្រាក់ (ចំណាយ)"
        amt_display = f"${amount:,.2f}" if currency == "USD" else f"{amount:,.0f} ៛"
        
        msg = (
            f"🧾 **ស្កេនបង្កាន់ដៃធនាគារជោគជ័យ!** (ID: {trans_id})\n"
            f"🏦 ធនាគារ: **{bank_name}**\n"
            f"🔄 ប្រភេទ: **{type_emoji}**\n"
            f"💰 ទឹកប្រាក់: **{amt_display}** ({currency})\n"
            f"📂 ផ្នែក: {bank_name}\n"
            f"📝 បរិយាយ: {desc}\n\n"
            f"*(កែប្រែ: `/edit {trans_id} [ចំនួន] [ផ្នែក] [បរិយាយ]` ឬលុប: `/delete {trans_id}`)*"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
    else:
        await update.message.reply_text(
            "⚠️ មិនអាចស្វែងរកទឹកប្រាក់ពីបង្កាន់ដៃនេះបានដោយស្វ័យប្រវត្តិទេ។\n"
            "សូមបញ្ចូលដោយដៃតាមគំរូ៖\n"
            "• ដុល្លារ: `- 15$ ធនាគារ ផ្ទេរប្រាក់`\n"
            "• រៀល: `- 60000៛ ធនាគារ ផ្ទេរប្រាក់`"
        )

# ----------------- បង្កើត Chart -----------------
def generate_finance_chart(records, title, start_date, end_date, currency_filter=None):
    if currency_filter:
        filtered = [r for r in records if r[2] == currency_filter]
    else:
        filtered = records

    if not filtered:
        return None

    currencies = list(dict.fromkeys(r[2] for r in filtered))
    donut_colors = ['#FF6B6B', '#4ECDC4', '#FFE66D', '#1A535C', '#F7B801', '#9B5DE5', '#00BBF9', '#00F5D4']

    # Single Currency
    if len(currencies) == 1:
        cur = currencies[0]
        cur_recs = filtered
        inc = sum(r[3] for r in cur_recs if r[0] == 'income')
        exp = sum(r[3] for r in cur_recs if r[0] == 'expense')
        
        breakdown_dict = {}
        for r in cur_recs:
            if r[0] == ('expense' if exp > 0 else 'income'):
                breakdown_dict[r[1]] = breakdown_dict.get(r[1], 0.0) + r[3]
        
        fmt = lambda v: f"${v:,.2f}" if cur == "USD" else f"{v:,.0f} ៛"
        
        fig = plt.figure(figsize=(10, 5), dpi=150)
        fig.patch.set_facecolor('#1E1E2E')

        ax1 = fig.add_subplot(1, 2, 1)
        ax2 = fig.add_subplot(1, 2, 2)

        categories = ['ចំណូល (Income)', 'ចំណាយ (Expense)']
        amounts = [inc, exp]
        colors = ['#2ECC71', '#E74C3C']

        bars = ax1.bar(categories, amounts, color=colors, width=0.45, edgecolor='#FFFFFF', linewidth=0.5)
        ax1.set_facecolor('#2A2B3D')
        ax1.set_title(f'ចំណូល vs ចំណាយ ({cur})', color='#FFFFFF', fontsize=12, fontweight='bold', pad=12)
        ax1.tick_params(colors='#D0D0D0', labelsize=10)
        ax1.spines['bottom'].set_color('#555566')
        ax1.spines['left'].set_color('#555566')
        ax1.spines['top'].set_visible(False)
        ax1.spines['right'].set_visible(False)
        ax1.yaxis.grid(True, linestyle='--', alpha=0.3, color='#888888')

        for bar in bars:
            height = bar.get_height()
            ax1.annotate(fmt(height),
                         xy=(bar.get_x() + bar.get_width() / 2, height),
                         xytext=(0, 4),
                         textcoords='offset points',
                         ha='center', va='bottom',
                         color='#FFFFFF', fontsize=10, fontweight='bold')

        ax2.set_facecolor('#1E1E2E')
        breakdown_title = f'ចំណាត់ថ្នាក់ចំណាយ ({cur})' if exp > 0 else f'ចំណាត់ថ្នាក់ចំណូល ({cur})'
        ax2.set_title(breakdown_title, color='#FFFFFF', fontsize=12, fontweight='bold', pad=12)

        labels = list(breakdown_dict.keys())
        values = list(breakdown_dict.values())
        if labels:
            c_palette = donut_colors * ((len(labels) // len(donut_colors)) + 1)
            wedges, texts, autotexts = ax2.pie(
                values,
                labels=labels,
                autopct='%1.1f%%',
                startangle=140,
                colors=c_palette[:len(labels)],
                wedgeprops=dict(width=0.4, edgecolor='#1E1E2E', linewidth=2),
                textprops=dict(color='#EAEAEA', fontsize=9),
                pctdistance=0.75
            )
            for autotext in autotexts:
                autotext.set_color('#FFFFFF')
                autotext.set_fontweight('bold')
                autotext.set_fontsize(8)
        else:
            ax2.axis('off')

        plt.suptitle(f'របាយការណ៍ហិរញ្ញវត្ថុ {title} ({cur})\n{start_date} ដល់ {end_date}',
                     color='#F1F2F6', fontsize=13, fontweight='bold', y=0.98)
        plt.tight_layout(rect=[0, 0.03, 1, 0.93])

        buf = BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', facecolor=fig.get_facecolor(), edgecolor='none')
        plt.close(fig)
        buf.seek(0)
        return buf

    else:
        # Both USD & KHR (2x2 Grid)
        fig, axes = plt.subplots(2, 2, figsize=(11, 8), dpi=150)
        fig.patch.set_facecolor('#1E1E2E')

        for row_idx, cur in enumerate(['USD', 'KHR']):
            cur_recs = [r for r in filtered if r[2] == cur]
            inc = sum(r[3] for r in cur_recs if r[0] == 'income')
            exp = sum(r[3] for r in cur_recs if r[0] == 'expense')
            breakdown_dict = {}
            for r in cur_recs:
                if r[0] == ('expense' if exp > 0 else 'income'):
                    breakdown_dict[r[1]] = breakdown_dict.get(r[1], 0.0) + r[3]

            fmt = lambda v, c=cur: f"${v:,.2f}" if c == "USD" else f"{v:,.0f} ៛"

            ax_bar = axes[row_idx, 0]
            ax_pie = axes[row_idx, 1]

            bars = ax_bar.bar(['ចំណូល', 'ចំណាយ'], [inc, exp], color=['#2ECC71', '#E74C3C'], width=0.45, edgecolor='#FFFFFF', linewidth=0.5)
            ax_bar.set_facecolor('#2A2B3D')
            ax_bar.set_title(f'ចំណូល vs ចំណាយ ({cur})', color='#FFFFFF', fontsize=11, fontweight='bold')
            ax_bar.tick_params(colors='#D0D0D0', labelsize=9)
            ax_bar.spines['bottom'].set_color('#555566')
            ax_bar.spines['left'].set_color('#555566')
            ax_bar.spines['top'].set_visible(False)
            ax_bar.spines['right'].set_visible(False)
            ax_bar.yaxis.grid(True, linestyle='--', alpha=0.3, color='#888888')

            for bar in bars:
                height = bar.get_height()
                ax_bar.annotate(fmt(height),
                                xy=(bar.get_x() + bar.get_width() / 2, height),
                                xytext=(0, 3),
                                textcoords='offset points',
                                ha='center', va='bottom',
                                color='#FFFFFF', fontsize=9, fontweight='bold')

            ax_pie.set_facecolor('#1E1E2E')
            ax_pie.set_title(f'ចំណាត់ថ្នាក់ ({cur})', color='#FFFFFF', fontsize=11, fontweight='bold')

            labels = list(breakdown_dict.keys())
            values = list(breakdown_dict.values())
            if labels:
                c_palette = donut_colors * ((len(labels) // len(donut_colors)) + 1)
                wedges, texts, autotexts = ax_pie.pie(
                    values,
                    labels=labels,
                    autopct='%1.1f%%',
                    startangle=140,
                    colors=c_palette[:len(labels)],
                    wedgeprops=dict(width=0.4, edgecolor='#1E1E2E', linewidth=1.5),
                    textprops=dict(color='#EAEAEA', fontsize=8),
                    pctdistance=0.75
                )
                for autotext in autotexts:
                    autotext.set_color('#FFFFFF')
                    autotext.set_fontweight('bold')
                    autotext.set_fontsize(7.5)
            else:
                ax_pie.axis('off')

        plt.suptitle(f'របាយការណ៍ហិរញ្ញវត្ថុ {title} (USD & KHR)\n{start_date} ដល់ {end_date}',
                     color='#F1F2F6', fontsize=13, fontweight='bold', y=0.98)
        plt.tight_layout(rect=[0, 0.03, 1, 0.94])

        buf = BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', facecolor=fig.get_facecolor(), edgecolor='none')
        plt.close(fig)
        buf.seek(0)
        return buf

# ----------------- ទម្រង់របាយការណ៍សង្ខេប -----------------
def build_report_text_and_keyboard(records, start_date, end_date, title, data_tag):
    usd_income = 0.0
    usd_expense = 0.0
    usd_breakdown = []

    khr_income = 0.0
    khr_expense = 0.0
    khr_breakdown = []

    for r_type, cat, cur, amt, count in records:
        if cur == "KHR":
            if r_type == "income":
                khr_income += amt
                khr_breakdown.append(f"  • [ចំណូល] {cat}: +{amt:,.0f} ៛ ({count} ដង)")
            else:
                khr_expense += amt
                khr_breakdown.append(f"  • [ចំណាយ] {cat}: -{amt:,.0f} ៛ ({count} ដង)")
        else:
            if r_type == "income":
                usd_income += amt
                usd_breakdown.append(f"  • [ចំណូល] {cat}: +${amt:,.2f} ({count} ដង)")
            else:
                usd_expense += amt
                usd_breakdown.append(f"  • [ចំណាយ] {cat}: -${amt:,.2f} ({count} ដង)")
                
    usd_balance = usd_income - usd_expense
    khr_balance = khr_income - khr_expense
    
    msg_parts = [
        f"📊 **របាយការណ៍ {title}**",
        f"ចន្លោះ: `{start_date}` ដល់ `{end_date}`",
        "-----------------------------"
    ]

    has_any = bool(records)
    if not has_any:
        msg_parts.append("មិនមានទិន្នន័យក្នុងចន្លោះពេលនេះឡើយ។")
    else:
        if usd_income > 0 or usd_expense > 0 or not khr_breakdown:
            usd_text = "\n".join(usd_breakdown) if usd_breakdown else "  (គ្មានប្រតិបត្តិការ)"
            msg_parts.extend([
                "💵 **គណនីដុល្លារ (USD)**:",
                usd_text,
                f"  សរុបចំណូល: +${usd_income:,.2f}",
                f"  សរុបចំណាយ: -${usd_expense:,.2f}",
                f"  សមតុល្យដុល្លារ: **${usd_balance:,.2f}**",
                "-----------------------------"
            ])
            
        if khr_income > 0 or khr_expense > 0:
            khr_text = "\n".join(khr_breakdown) if khr_breakdown else "  (គ្មានប្រតិបត្តិការ)"
            msg_parts.extend([
                "🇰🇭 **គណនីរៀល (KHR)**:",
                khr_text,
                f"  សរុបចំណូល: +{khr_income:,.0f} ៛",
                f"  សរុបចំណាយ: -{khr_expense:,.0f} ៛",
                f"  សមតុល្យរៀល: **{khr_balance:,.0f} ៛**",
                "-----------------------------"
            ])

    msg = "\n".join(msg_parts)
    
    keyboard = []
    if has_any:
        has_usd = any(r[2] == 'USD' for r in records)
        has_khr = any(r[2] == 'KHR' for r in records)
        
        if has_usd and has_khr:
            keyboard.append([
                InlineKeyboardButton("📊 Chart រួម ($ & ៛)", callback_data=f"chart_{data_tag}_ALL"),
                InlineKeyboardButton("💵 Chart ($)", callback_data=f"chart_{data_tag}_USD"),
                InlineKeyboardButton("🇰🇭 Chart (៛)", callback_data=f"chart_{data_tag}_KHR")
            ])
        elif has_khr:
            keyboard.append([InlineKeyboardButton("🇰🇭 បង្ហាញក្រាហ្វិក (Chart ៛)", callback_data=f"chart_{data_tag}_KHR")])
        else:
            keyboard.append([InlineKeyboardButton("💵 បង្ហាញក្រាហ្វិក (Chart $)", callback_data=f"chart_{data_tag}_USD")])
            
    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    return msg, reply_markup

# ----------------- របាយការណ៍បែងចែកពេលវេលា & រូបិយប័ណ្ណ -----------------
async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not db.is_registered(user_id):
        await update.message.reply_text("សូមចុះឈ្មោះជាមុនដោយវាយ /start")
        return

    # ករណី User បញ្ចូល Custom Date: /report 2026-09-01 2026-09-25
    if context.args:
        start_date = None
        end_date = None
        if len(context.args) >= 2:
            start_date = parse_date_argument(context.args[0])
            end_date = parse_date_argument(context.args[1])
        elif len(context.args) == 1:
            start_date = end_date = parse_date_argument(context.args[0])
            
        if start_date and end_date:
            if start_date > end_date:
                start_date, end_date = end_date, start_date
            title = f"{start_date} ដល់ {end_date}" if start_date != end_date else start_date
            records = db.get_report(user_id, start_date, end_date)
            msg, reply_markup = build_report_text_and_keyboard(records, start_date, end_date, title, f"custom_{start_date}_{end_date}")
            await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=reply_markup)
            return
        else:
            await update.message.reply_text(
                "⚠️ កាលបរិច្ឆេទមិនត្រឹមត្រូវ! គំរូ:\n"
                "• `/report 2026-09-01 2026-09-25`\n"
                "• `/report 01/09/2026 25/09/2026`\n"
                "• `/report 2026-09-25`",
                parse_mode="Markdown"
            )
            return

    keyboard = [
        [InlineKeyboardButton("📅 ប្រចាំថ្ងៃ", callback_data="rep_daily"),
         InlineKeyboardButton("📅 ប្រចាំសប្ដាហ៍", callback_data="rep_weekly")],
        [InlineKeyboardButton("📅 ប្រចាំខែ", callback_data="rep_monthly"),
         InlineKeyboardButton("📅 ប្រចាំត្រីមាស", callback_data="rep_quarterly")],
        [InlineKeyboardButton("📅 ប្រចាំឆមាស", callback_data="rep_semiannual"),
         InlineKeyboardButton("📅 ប្រចាំឆ្នាំ", callback_data="rep_yearly")],
        [InlineKeyboardButton("🗓 កំណត់ថ្ងៃតាមចិត្ត (Custom Date)", callback_data="rep_custom_hint")],
        [InlineKeyboardButton("🏦 សរុបបង្កាន់ដៃធនាគារ (Bank Slips)", callback_data="rep_bank_slips")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("សូមជ្រើសរើសចន្លោះពេលដើម្បីមើលរបាយការណ៍៖", reply_markup=reply_markup)

async def report_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    
    # បង្ហាញការណែនាំ Custom Date
    if data == "rep_custom_hint":
        hint_text = (
            "🗓 **របៀបមើលរបាយការណ៍ និង Chart តាមថ្ងៃកំណត់ (Custom Date)៖**\n\n"
            "🔹 **មើលរបាយការណ៍សង្ខេប៖**\n"
            "• `/report [ថ្ងៃចាប់ផ្ដើម] [ថ្ងៃបញ្ចប់]`\n"
            "  ឧទាហរណ៍: `/report 2026-09-01 2026-09-25`\n"
            "  ឬ: `/report 01/09/2026 25/09/2026`\n"
            "• មើលតែមួយថ្ងៃ: `/report 2026-09-25`\n\n"
            "🔹 **មើលក្រាហ្វិក (Chart)៖**\n"
            "• `/chart [ថ្ងៃចាប់ផ្ដើម] [ថ្ងៃបញ្ចប់]`\n"
            "  ឧទាហរណ៍: `/chart 2026-09-01 2026-09-25`\n\n"
            "🔹 **មើលបូកសរុបបង្កាន់ដៃធនាគារ៖**\n"
            "• `/bank [ថ្ងៃចាប់ផ្ដើម] [ថ្ងៃបញ្ចប់]`\n"
            "  ឧទាហរណ៍: `/bank 2026-09-01 2026-09-25`\n"
            "• ឬវាយ `/bank` ដើម្បីមើលសរុបទាំងអស់"
        )
        await query.message.reply_text(hint_text, parse_mode="Markdown")
        return

    # សរុបបង្កាន់ដៃធនាគារ
    if data == "rep_bank_slips":
        records = db.get_bank_slips_summary(user_id)
        text_msg = format_bank_slips_report(records, "គ្រប់ពេលវេលា")
        keyboard = []
        if records:
            keyboard.append([InlineKeyboardButton("📊 មើល Chart បង្កាន់ដៃធនាគារ", callback_data="chart_bank_all")])
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        await query.message.reply_text(text_msg, parse_mode="Markdown", reply_markup=reply_markup)
        return

    start_date, end_date, title = get_date_range_and_title(data)
    if not start_date:
        return

    records = db.get_report(user_id, start_date, end_date)
    msg, reply_markup = build_report_text_and_keyboard(records, start_date, end_date, title, data)
    await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=reply_markup)

# ----------------- បូកសរុបបង្កាន់ដៃគ្រប់ធនាគារ (/bank) -----------------
def format_bank_slips_report(records, title):
    if not records:
        return f"🏦 **បូកសរុបបង្កាន់ដៃគ្រប់ធនាគារ (Bank Payslip Summary)**\nចន្លោះពេល: `{title}`\n----------------------------------\nមិនមានទិន្នន័យបង្កាន់ដៃធនាគារឡើយ។"
        
    bank_data = {}
    usd_income = 0.0
    usd_expense = 0.0
    khr_income = 0.0
    khr_expense = 0.0
    
    for bank, cur, r_type, amt, count in records:
        if bank not in bank_data:
            bank_data[bank] = {"USD": {"income": 0.0, "expense": 0.0, "count": 0},
                               "KHR": {"income": 0.0, "expense": 0.0, "count": 0}}
        bank_data[bank][cur][r_type] += amt
        bank_data[bank][cur]["count"] += count
        
        if cur == "USD":
            if r_type == "income":
                usd_income += amt
            else:
                usd_expense += amt
        else:
            if r_type == "income":
                khr_income += amt
            else:
                khr_expense += amt

    lines = [
        f"🏦 **បូកសរុបបង្កាន់ដៃគ្រប់ធនាគារ (Bank Payslips)**",
        f"ចន្លោះពេល: `{title}`",
        "----------------------------------"
    ]
    
    for bank, cur_dict in bank_data.items():
        lines.append(f"🔹 **{bank}**:")
        has_items = False
        usd = cur_dict["USD"]
        if usd["income"] > 0:
            lines.append(f"  • ចំណូល: +${usd['income']:,.2f}")
            has_items = True
        if usd["expense"] > 0:
            lines.append(f"  • ចំណាយ: -${usd['expense']:,.2f}")
            has_items = True
            
        khr = cur_dict["KHR"]
        if khr["income"] > 0:
            lines.append(f"  • ចំណូល: +{khr['income']:,.0f} ៛")
            has_items = True
        if khr["expense"] > 0:
            lines.append(f"  • ចំណាយ: -{khr['expense']:,.0f} ៛")
            has_items = True
            
        total_slips = usd["count"] + khr["count"]
        lines.append(f"  (សរុប {total_slips} សន្លឹក)")
        lines.append("")

    usd_bal = usd_income - usd_expense
    khr_bal = khr_income - khr_expense
    
    lines.extend([
        "----------------------------------",
        "💰 **សរុបរួមពីគ្រប់ធនាគារទាំងអស់**:",
        "💵 **ដុល្លារ (USD)**:",
        f"  • ចំណូល: +${usd_income:,.2f}",
        f"  • ចំណាយ: -${usd_expense:,.2f}",
        f"  • សមតុល្យ: **${usd_bal:,.2f}**",
        "",
        "🇰🇭 **រៀល (KHR)**:",
        f"  • ចំណូល: +{khr_income:,.0f} ៛",
        f"  • ចំណាយ: -{khr_expense:,.0f} ៛",
        f"  • សមតុល្យ: **{khr_bal:,.0f} ៛**"
    ])
    
    return "\n".join(lines)

async def bank_slips_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not db.is_registered(user_id):
        await update.message.reply_text("សូមចុះឈ្មោះជាមុនដោយវាយ /start")
        return

    start_date = None
    end_date = None
    title = "គ្រប់ពេលវេលា"
    if len(context.args) >= 2:
        sd = parse_date_argument(context.args[0])
        ed = parse_date_argument(context.args[1])
        if sd and ed:
            start_date, end_date = (sd, ed) if sd <= ed else (ed, sd)
            title = f"{start_date} ដល់ {end_date}"
    elif len(context.args) == 1:
        d = parse_date_argument(context.args[0])
        if d:
            start_date = end_date = d
            title = start_date

    records = db.get_bank_slips_summary(user_id, start_date, end_date)
    text_msg = format_bank_slips_report(records, title)

    keyboard = []
    if records:
        cb_val = f"chart_bank_{start_date}_{end_date}" if start_date and end_date else "chart_bank_all"
        keyboard.append([InlineKeyboardButton("📊 មើល Chart បង្កាន់ដៃធនាគារ", callback_data=cb_val)])
    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    
    await update.message.reply_text(text_msg, parse_mode="Markdown", reply_markup=reply_markup)

# ----------------- បង្ហាញ Chart (ក្រាហ្វិក) -----------------
async def chart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not db.is_registered(user_id):
        await update.message.reply_text("សូមចុះឈ្មោះជាមុនដោយវាយ /start")
        return

    # ករណី Custom Date: /chart 2026-09-01 2026-09-25
    if context.args:
        start_date = None
        end_date = None
        if len(context.args) >= 2:
            start_date = parse_date_argument(context.args[0])
            end_date = parse_date_argument(context.args[1])
        elif len(context.args) == 1:
            start_date = end_date = parse_date_argument(context.args[0])
            
        if start_date and end_date:
            if start_date > end_date:
                start_date, end_date = end_date, start_date
            title = f"{start_date} ដល់ {end_date}" if start_date != end_date else start_date
            records = db.get_report(user_id, start_date, end_date)
            chart_buf = generate_finance_chart(records, title, start_date, end_date)
            if chart_buf:
                await update.message.reply_photo(photo=chart_buf, caption=f"📊 **ក្រាហ្វិករបាយការណ៍ហិរញ្ញវត្ថុ**\nចន្លោះ: `{start_date}` ដល់ `{end_date}`", parse_mode="Markdown")
            else:
                await update.message.reply_text(f"⚠️ មិនមានទិន្នន័យសម្រាប់បង្កើតក្រាហ្វិក ({start_date} ដល់ {end_date}) ឡើយ។")
            return
        else:
            await update.message.reply_text(
                "⚠️ កាលបរិច្ឆេទមិនត្រឹមត្រូវ! គំរូ:\n"
                "• `/chart 2026-09-01 2026-09-25`\n"
                "• `/chart 01/09/2026 25/09/2026`",
                parse_mode="Markdown"
            )
            return

    keyboard = [
        [InlineKeyboardButton("📊 ប្រចាំថ្ងៃ", callback_data="chart_rep_daily_ALL"),
         InlineKeyboardButton("📊 ប្រចាំសប្ដាហ៍", callback_data="chart_rep_weekly_ALL")],
        [InlineKeyboardButton("📊 ប្រចាំខែ", callback_data="chart_rep_monthly_ALL"),
         InlineKeyboardButton("📊 ប្រចាំត្រីមាស", callback_data="chart_rep_quarterly_ALL")],
        [InlineKeyboardButton("📊 ប្រចាំឆមាស", callback_data="chart_rep_semiannual_ALL"),
         InlineKeyboardButton("📊 ប្រចាំឆ្នាំ", callback_data="chart_rep_yearly_ALL")],
        [InlineKeyboardButton("🗓 កំណត់ថ្ងៃតាមចិត្ត (Custom Date)", callback_data="rep_custom_hint")],
        [InlineKeyboardButton("🏦 ក្រាហ្វិកបង្កាន់ដៃធនាគារ", callback_data="chart_bank_all")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📊 សូមជ្រើសរើសចន្លោះពេលដើម្បីបង្កើត Chart ក្រាហ្វិក៖", reply_markup=reply_markup)

async def chart_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    raw_data = query.data.replace("chart_", "")
    user_id = query.from_user.id

    # ករណី Chart បង្កាន់ដៃធនាគារ
    if raw_data.startswith("bank_"):
        bank_part = raw_data.replace("bank_", "")
        if bank_part == "all":
            start_date, end_date, title = None, None, "គ្រប់ពេលវេលា"
        else:
            p = bank_part.split("_")
            start_date, end_date = p[0], p[1]
            title = f"{start_date} ដល់ {end_date}"
            
        slips = db.get_bank_slips_summary(user_id, start_date, end_date)
        # បំប្លែងទៅទម្រង់ records: type, category, cur, amount, count
        chart_records = [(r[2], r[0], r[1], r[3], r[4]) for r in slips]
        s_date_display = start_date if start_date else "ដើមដំបូង"
        e_date_display = end_date if end_date else "បច្ចុប្បន្ន"
        chart_buf = generate_finance_chart(chart_records, f"បង្កាន់ដៃធនាគារ ({title})", s_date_display, e_date_display)
        if chart_buf:
            caption = f"🏦 **ក្រាហ្វិកបូកសរុបបង្កាន់ដៃធនាគារ ({title})**"
            await query.message.reply_photo(photo=chart_buf, caption=caption, parse_mode="Markdown")
        else:
            await query.message.reply_text(f"⚠️ មិនមានទិន្នន័យបង្កាន់ដៃធនាគារសម្រាប់បង្កើតក្រាហ្វិកឡើយ។")
        return

    parts = raw_data.split("_")
    if len(parts) >= 3 and parts[-1] in ("ALL", "USD", "KHR"):
        cur_filter = None if parts[-1] == "ALL" else parts[-1]
        data_key = "_".join(parts[:-1])
    else:
        cur_filter = None
        data_key = raw_data

    start_date, end_date, title = get_date_range_and_title(data_key)
    if not start_date:
        return

    records = db.get_report(user_id, start_date, end_date)
    chart_buf = generate_finance_chart(records, title, start_date, end_date, currency_filter=cur_filter)

    if chart_buf:
        filter_label = f"({cur_filter})" if cur_filter else "($ & ៛)"
        caption = f"📊 **ក្រាហ្វិករបាយការណ៍ហិរញ្ញវត្ថុ {title} {filter_label}**\nចន្លោះ: `{start_date}` ដល់ `{end_date}`"
        await query.message.reply_photo(photo=chart_buf, caption=caption, parse_mode="Markdown")
    else:
        await query.message.reply_text(f"⚠️ មិនមានទិន្នន័យសម្រាប់បង្កើតក្រាហ្វិក {title} (`{start_date}` ដល់ `{end_date}`) ឡើយ។")

# ----------------- ធ្វើបច្ចុប្បន្នភាព និងលុប (Update/Edit) -----------------
async def edit_record(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ឧទាហរណ៍: /edit 1 25.50$ ម្ហូប ញ៉ាំបាយ ឬ /edit 1 100000៛ ម្ហូប ញ៉ាំបាយ
    user_id = update.effective_user.id
    args = context.args
    
    if len(args) < 3:
        await update.message.reply_text(
            "ទម្រង់ខុស! គំរូ:\n"
            "• `/edit [ID] [ចំនួន$ ឬ ៛] [ផ្នែក] [បរិយាយ]`\n"
            "  ឧទាហរណ៍: `/edit 1 25.50$ ម្ហូប ញ៉ាំបាយ` ឬ `/edit 1 60000៛ ម្ហូប ញ៉ាំបាយ`",
            parse_mode="Markdown"
        )
        return
        
    try:
        trans_id = int(args[0])
        amt_str = args[1]
        
        # ពិនិត្យមើលរូបិយប័ណ្ណ
        currency = None
        if re.search(r"៛|khr|r", amt_str, re.I):
            currency = "KHR"
        elif re.search(r"\$|usd", amt_str, re.I):
            currency = "USD"
            
        clean_amt_str = re.sub(r"[^\d.]", "", amt_str)
        amount = float(clean_amt_str)
        category = args[2]
        desc = " ".join(args[3:]) if len(args) > 3 else "កែប្រែថ្មី"
        
        ok = db.update_transaction(trans_id, user_id, amount=amount, currency=currency, category=category, description=desc)
        if ok:
            cur_display = f"({currency})" if currency else ""
            await update.message.reply_text(f"✅ បានធ្វើបច្ចុប្បន្នភាពប្រតិបត្តិការ ID {trans_id} {cur_display} រួចរាល់!")
        else:
            await update.message.reply_text("❌ រកមិនឃើញ ID ឬអ្នកគ្មានសិទ្ធិកែប្រែប្រតិបត្តិការនេះឡើយ។")
    except ValueError:
        await update.message.reply_text("❌ ទឹកប្រាក់ ឬ ID ត្រូវតែជាលេខ។")

async def delete_record(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    app.add_handler(CommandHandler("bank", bank_slips_command))
    app.add_handler(CommandHandler("slips", bank_slips_command))
    app.add_handler(CommandHandler("edit", edit_record))
    app.add_handler(CommandHandler("delete", delete_record))
    
    app.add_handler(CallbackQueryHandler(chart_callback, pattern="^chart_"))
    app.add_handler(CallbackQueryHandler(report_callback, pattern="^rep_"))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_record))
    
    print("Bot is running with Bank Payslip aggregator & Custom Date support...")
    app.run_polling()

if __name__ == "__main__":
    main()
