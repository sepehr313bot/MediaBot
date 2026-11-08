import os
import logging
import sqlite3
import requests
import time
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import yt_dlp
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from deep_translator import GoogleTranslator

# ================= ⚙️ تنظیمات اصلی =================
# ⚠️ توکن رباتت رو اینجا بذار:
TOKEN = '8810935161:AAH5YOqCeAMPM010z-XErz4pntu26Fp873c'

ADMIN_ID = 7289902597
ADMIN_USERNAME = 'Mohammad_Sepehr_Moradi'
CARD_NUMBER = "6037997701584816"
USDT_ADDRESS = "TX1cN1yxc2yYK7PjxLrvBte4uv8jgEkoNT" 
VIP_PRICE = 300000
VIP_PRICE_STR = "300,000 تومان"
AI_API_URL = "https://text.pollinations.ai/"
FORCE_JOIN_CHANNEL = 'Media_Land_MrMoradi' 

DB_NAME = 'new_database.db'
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# ================= 🌍 دیکشنری زبان‌ها =================
LANGUAGES = [
    ("fa", "🇮🇷 فارسی (Iran)"), ("en", "🇬🇧 English (UK)"), ("ar", "🇸🇦 العربية (Arabic)"), ("zh-CN", "🇨🇳 中文 (Chinese)"),
    ("es", "🇪🇸 Español"), ("fr", "🇫🇷 Français"), ("de", "🇩🇪 Deutsch"), ("ru", "🇷🇺 Русский"),
    ("tr", "🇹🇷 Türkçe"), ("hi", "🇮🇳 हिन्दी"), ("ja", "🇯🇵 日本語"), ("ko", "🇰🇷 한국어"),
    ("pt", "🇵🇹 Português"), ("it", "🇮🇹 Italiano"), ("nl", "🇳🇱 Nederlands"), ("sv", "🇸🇪 Svenska"),
    ("pl", "🇵🇱 Polski"), ("uk", "🇺🇦 Українська"), ("ro", "🇷🇴 Română"), ("el", "🇬🇷 Ελληνικά"),
]

# ================= 📝 مترجم =================
def get_text(key, lang_code):
    texts = {
        'ai_welcome': "🤖 **به بخش هوش مصنوعی خوش آمدید!**\n\nهر سوالی داری بپرس تا جواب بدم.\nبرای خروج، دکمه زیر رو بزن.",
        'limit': "⚠️ **سقف دانلود رایگان شما تمام شده!**\nبرای دانلود نامحدود، اشتراک VIP تهیه کنید.",
        'processing': "⏳ در حال پردازش لینک...",
        'too_large': "📥 حجم این فایل بیشتر از ۵۰ مگابایت است.\n\n👇 لینک دانلود مستقیم:\n{}",
        'vip_text': f"💳 **خرید اشتراک VIP**\n\n💰 هزینه: {VIP_PRICE_STR}\n\n💳 کارت:\n`{CARD_NUMBER}`\n\n🪙 تتر (TRC20):\n`{USDT_ADDRESS}`\n\n⚠️ رسید را برای مدیر بفرستید.",
        'status_vip': "✅ شما **VIP** هستید.\n📅 تا: {}",
        'status_free': "👤 شما **عادی** هستید.\n📥 دانلود باقی‌مانده: **{}** از ۳",
        'error': "❌ خطا:\n`{}`"
    }
    if lang_code == 'fa': return texts[key]
    try: return GoogleTranslator(source='auto', target=lang_code).translate(texts[key])
    except: return texts[key]

# ================= 🗄️ دیتابیس =================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY, first_name TEXT, username TEXT,
                        phone TEXT, downloads INTEGER DEFAULT 0, last_reset TIMESTAMP,
                        is_vip INTEGER DEFAULT 0, vip_expiry TIMESTAMP, lang TEXT DEFAULT 'fa',
                        bonus_downloads INTEGER DEFAULT 0, score INTEGER DEFAULT 0,
                        last_msg_time REAL DEFAULT 0
                    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS activity_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, action TEXT, details TEXT, timestamp TIMESTAMP
                    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS promos (
                        code TEXT PRIMARY KEY, discount INTEGER, max_uses INTEGER, uses INTEGER DEFAULT 0
                    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS payments (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount TEXT, status TEXT, timestamp TIMESTAMP
                    )''')
    conn.commit()
    cursor.execute("PRAGMA table_info(users)")
    columns = [info[1] for info in cursor.fetchall()]
    if 'score' not in columns: cursor.execute("ALTER TABLE users ADD COLUMN score INTEGER DEFAULT 0")
    if 'last_msg_time' not in columns: cursor.execute("ALTER TABLE users ADD COLUMN last_msg_time REAL DEFAULT 0")
    conn.commit()
    conn.close()

def log_activity(user_id, action, details=""):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT INTO activity_logs (user_id, action, details, timestamp) VALUES (?, ?, ?, ?)", (user_id, action, details, now))
    conn.commit()
    conn.close()

def add_score(user_id, amount):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET score = score + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def register_user(user_id, first_name, username, referrer_id=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        now = datetime.now()
        cursor.execute("INSERT INTO users (user_id, first_name, username, last_reset) VALUES (?, ?, ?, ?)", (user_id, first_name, username, now))
        conn.commit()
        conn.close()
        add_score(user_id, 10)
        if referrer_id and referrer_id != user_id:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET bonus_downloads = bonus_downloads + 1 WHERE user_id = ?", (referrer_id,))
            conn.commit()
            conn.close()
            return True, referrer_id
        return True, None
    conn.close()
    return False, None

def get_user_status(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT downloads, last_reset, is_vip, vip_expiry, lang, bonus_downloads, score FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    if not user: return None
    downloads, last_reset_str, is_vip, vip_expiry_str, lang, bonus_downloads, score = user
    last_reset = datetime.fromisoformat(last_reset_str) if last_reset_str else datetime.now()
    now = datetime.now()
    if is_vip and vip_expiry_str:
        vip_expiry = datetime.fromisoformat(vip_expiry_str)
        if now > vip_expiry: is_vip = 0
    if (now - last_reset).days >= 7:
        downloads = 0
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET downloads = 0, last_reset = ? WHERE user_id = ?", (now, user_id))
        conn.commit()
        conn.close()
    return {'downloads': downloads, 'is_vip': is_vip, 'vip_expiry': vip_expiry_str, 'lang': lang, 'bonus': bonus_downloads, 'score': score}

def increment_download(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT bonus_downloads FROM users WHERE user_id = ?", (user_id,))
    bonus = cursor.fetchone()[0]
    if bonus > 0: cursor.execute("UPDATE users SET bonus_downloads = bonus_downloads - 1 WHERE user_id = ?", (user_id,))
    else: cursor.execute("UPDATE users SET downloads = downloads + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    add_score(user_id, 5)

def set_vip(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    expiry = datetime.now() + timedelta(days=30)
    cursor.execute("UPDATE users SET is_vip = 1, vip_expiry = ? WHERE user_id = ?", (expiry.isoformat(), user_id))
    conn.commit()
    conn.close()
    add_score(user_id, 50)

# ================= 🌐 وب سرور فیک =================
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running!")

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), DummyHandler)
    server.serve_forever()

# ================= 🛡️ چک عضویت =================
async def check_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        member = await context.bot.get_chat_member(chat_id=f"@{FORCE_JOIN_CHANNEL}", user_id=user_id)
        if member.status in ['member', 'administrator', 'creator']:
            return True
    except: pass
    return False

# ================= 🤖 هندلرها =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not await check_membership(update, context):
        keyboard = [[InlineKeyboardButton("📢 عضویت در کانال", url=f"https://t.me/{FORCE_JOIN_CHANNEL}")],
                    [InlineKeyboardButton("✅ عضو شدم", callback_data='check_join')]]
        await update.message.reply_text("⚠️ برای استفاده از ربات، ابتدا در کانال ما عضو شوید:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    referrer_id = None
    if context.args and context.args[0].startswith('ref_'):
        try: referrer_id = int(context.args[0].split('_')[1])
        except: pass
        
    is_new, inviter = register_user(user.id, user.first_name, user.username, referrer_id)
    status = get_user_status(user.id)
    lang = status['lang'] if status else 'fa'
    
    if is_new:
        report = f"🚨 **کاربر جدید!**\n👤 {user.first_name}\n🆔 `{user.id}`"
        await context.bot.send_message(chat_id=ADMIN_ID, text=report, parse_mode='Markdown')
    if inviter:
        await context.bot.send_message(chat_id=inviter, text="🎉 یکی از دوستانت با لینک تو اومد! ۱ دانلود هدیه گرفتی.")

    if lang == 'fa':
        welcome_text = (
            f"سلام {user.first_name} عزیز! 👋\n\n"
            "به **مولتی‌مدیا لند (Mr Moradi)** خوش اومدی! 🌍✨\n\n"
            "من یه ابرربات هوشمندم که می‌تونم:\n"
            "📥 **دانلود ویدیو** از تمام سایت‌های دنیا\n"
            "📄 **دانلود فایل‌های PDF و عکس** از هر لینکی\n"
            "🧠 **چت با هوش مصنوعی**\n"
            "🎮 **سیستم امتیازدهی**\n\n"
            "⚡ کافیه لینک رو برام بفرستی.\n\n"
            "👇 از دکمه‌های زیر استفاده کن:"
        )
    else:
        welcome_text = "Welcome! Send a link to download."

    keyboard = [
        [InlineKeyboardButton("🤖 چت با هوش مصنوعی", callback_data='ai_chat')],
        [InlineKeyboardButton("💎 خرید VIP", callback_data='buy_vip'), InlineKeyboardButton("🎁 کد تخفیف", callback_data='promo')],
        [InlineKeyboardButton("📊 وضعیت من", callback_data='my_status'), InlineKeyboardButton("🏆 برترین‌ها", callback_data='leaderboard')],
        [InlineKeyboardButton("📜 تاریخچه من", callback_data='my_history'), InlineKeyboardButton("🌐 تغییر زبان", callback_data='lang_menu')],
        [InlineKeyboardButton("📱 ارسال شماره", callback_data='send_phone'), InlineKeyboardButton("👥 دعوت دوستان", callback_data='referral')],
        [InlineKeyboardButton("🎬 اشتراک‌گذاری", callback_data='share_bot')],
        [InlineKeyboardButton("📢 عضویت در کانال", url=f"https://t.me/{FORCE_JOIN_CHANNEL}")],
        [InlineKeyboardButton("💬 ارتباط با مدیر", url=f"https://t.me/{ADMIN_USERNAME}")],
    ]
    await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    status = get_user_status(user_id)
    lang = status['lang'] if status else 'fa'

    if query.data == 'check_join':
        if await check_membership(update, context):
            await query.edit_message_text("✅ عضویت تایید شد! حالا /start را بزنید.")
        else:
            await query.answer("❌ شما هنوز عضو کانال نشده‌اید!", show_alert=True)

    elif query.data == 'referral':
        ref_link = f"https://t.me/{context.bot.username}?start=ref_{user_id}"
        await query.message.reply_text(f"👥 **دعوت دوستان**\n\nبا ارسال این لینک به دوستانتان، به ازای هر نفر ۱ دانلود رایگان هدیه بگیرید:\n\n`{ref_link}`", parse_mode='Markdown')
        
    elif query.data == 'share_bot':
        share_link = f"https://t.me/share/url?url=https://t.me/{context.bot.username}&text=بهترین ربات دانلود و هوش مصنوعی!"
        keyboard = [[InlineKeyboardButton("ارسال به دوستان", url=share_link)]]
        await query.message.reply_text("🎬 **اشتراک‌گذاری ربات**\n\nبا کلیک روی دکمه زیر، لینک ربات را برای دوستانتان بفرستید:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == 'lang_menu':
        keyboard = []
        for code, name in LANGUAGES:
            keyboard.append([InlineKeyboardButton(name, callback_data=f"set_lang_{code}")])
        await query.edit_message_text("🌐 لطفاً زبان خود را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith('set_lang_'):
        new_lang = query.data.replace('set_lang_', '')
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET lang = ? WHERE user_id = ?", (new_lang, user_id))
        conn.commit()
        conn.close()
        await query.edit_message_text("✅ زبان با موفقیت تغییر کرد. لطفاً دوباره /start را بزنید.")

    elif query.data == 'buy_vip':
        # 👇 تغییرات امنیتی تتر
        text = (
            f"💳 **خرید اشتراک VIP**\n\n"
            f"💰 هزینه: **{VIP_PRICE_STR}**\n\n"
            f"💳 **روش اول (کارت به کارت):**\n"
            f"`{CARD_NUMBER}`\n"
            f"*(بعد از واریز، عکس فیش رو بفرستید)*\n\n"
            f"🪙 **روش دوم (تتر - TRC20):**\n"
            f"`{USDT_ADDRESS}`\n"
            f"⚠️ **فقط شبکه TRC20!** در غیر این صورت پول از بین می‌رود.\n"
            f"*(بعد از واریز، کد TXID تراکنش را به صورت متن بفرستید)*"
        )
        await query.edit_message_text(text, parse_mode='Markdown')
        context.user_data['awaiting_txid'] = True
        
    elif query.data == 'my_status':
        if status['is_vip']:
            expiry = datetime.fromisoformat(status['vip_expiry']).strftime('%Y-%m-%d')
            await query.edit_message_text(get_text('status_vip', lang).format(expiry) + f"\n⭐ امتیاز شما: {status['score']}")
        else:
            remaining = max(0, 3 - status['downloads'] + status.get('bonus', 0))
            await query.edit_message_text(get_text('status_free', lang).format(remaining) + f"\n⭐ امتیاز شما: {status['score']}")

    elif query.data == 'leaderboard':
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT first_name, score FROM users ORDER BY score DESC LIMIT 10")
        top_users = cursor.fetchall()
        conn.close()
        text = "🏆 **۱۰ کاربر برتر:**\n\n"
        for idx, (name, score) in enumerate(top_users, 1):
            text += f"{idx}. {name} - {score} امتیاز\n"
        await query.edit_message_text(text, parse_mode='Markdown')

    elif query.data == 'my_history':
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT action, details, timestamp FROM activity_logs WHERE user_id = ? ORDER BY id DESC LIMIT 10", (user_id,))
        logs = cursor.fetchall()
        conn.close()
        history_text = "📜 **۱۰ فعالیت اخیر شما:**\n\n"
        if not logs: history_text = "📜 هنوز فعالیتی نداری."
        else:
            for log in logs: history_text += f"🔸 {log[0]} ({log[2]})\n"
        await query.edit_message_text(history_text, parse_mode='Markdown')
            
    elif query.data == 'send_phone':
        contact_button = KeyboardButton("ارسال شماره من", request_contact=True)
        reply_markup = ReplyKeyboardMarkup([[contact_button]], one_time_keyboard=True, resize_keyboard=True)
        await query.message.reply_text("روی دکمه زیر بزن:", reply_markup=reply_markup)
        
    elif query.data == 'ai_chat':
        context.user_data['awaiting_ai'] = True
        await query.edit_message_text(get_text('ai_welcome', lang), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ خروج", callback_data='exit_ai')]]))
    elif query.data == 'exit_ai':
        context.user_data['awaiting_ai'] = False
        await query.edit_message_text("✅ خارج شدی.")
    elif query.data == 'promo':
        await query.edit_message_text("🎁 کد تخفیف را ارسال کن:")
        context.user_data['awaiting_promo'] = True

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    status = get_user_status(user.id)
    lang = status['lang'] if status else 'fa'
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT last_msg_time FROM users WHERE user_id = ?", (user.id,))
    last_time = cursor.fetchone()[0]
    if last_time and (time.time() - last_time) < 5:
        conn.close()
        await update.message.reply_text("⚠️ ۵ ثانیه صبر کنید.")
        return
    cursor.execute("UPDATE users SET last_msg_time = ? WHERE user_id = ?", (time.time(), user.id))
    conn.commit()
    conn.close()

    # 👇 بررسی TXID تتر
    if context.user_data.get('awaiting_txid'):
        context.user_data['awaiting_txid'] = False
        txid = update.message.text.strip()
        
        info_msg = f"🪙 **TXID جدید!**\n👤 {user.first_name}\n🆔 `{user.id}`\n🔗 کد تراکنش: `{txid}`"
        keyboard = [[InlineKeyboardButton("✅ فعال کردن VIP", callback_data=f"approve_vip_{user.id}")]]
        
        await context.bot.send_message(chat_id=ADMIN_ID, text=info_msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        await update.message.reply_text("✅ کد تراکنش برای مدیریت ارسال شد. لطفاً منتظر تایید باشید.")
        return

    if context.user_data.get('awaiting_promo'):
        context.user_data['awaiting_promo'] = False
        code = update.message.text.upper()
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT discount, max_uses, uses FROM promos WHERE code = ?", (code,))
        promo = cursor.fetchone()
        if promo and promo[2] < promo[1]:
            discount = promo[0]
            new_price = VIP_PRICE - (VIP_PRICE * discount // 100)
            cursor.execute("UPDATE promos SET uses = uses + 1 WHERE code = ?", (code,))
            conn.commit()
            conn.close()
            await update.message.reply_text(f"✅ کد تخفیف اعمال شد! ({discount}% تخفیف)\n\n💰 قیمت جدید VIP برای شما: **{new_price:,} تومان**", parse_mode='Markdown')
        else:
            conn.close()
            await update.message.reply_text("❌ کد نامعتبر است.")
        return

    if update.message.contact:
        phone = update.message.contact.phone_number
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET phone = ? WHERE user_id = ?", (phone, user.id))
        conn.commit()
        conn.close()
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"📱 شماره جدید: {phone}\n👤 {user.first_name}\n🆔 `{user.id}`", parse_mode='Markdown')
        await update.message.reply_text("✅ شماره ارسال شد.", reply_markup=ReplyKeyboardRemove())
        return

    if update.message.photo:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO payments (user_id, amount, status, timestamp) VALUES (?, ?, ?, ?)", (user.id, "Unknown", "Pending", datetime.now()))
        conn.commit()
        conn.close()
        
        info_msg = f"🧾 **رسید جدید!**\n👤 {user.first_name}\n🆔 `{user.id}`\n\nبرای فعال‌سازی VIP، روی دکمه زیر بزن:"
        keyboard = [[InlineKeyboardButton("✅ فعال کردن VIP", callback_data=f"approve_vip_{user.id}")]]
        
        await context.bot.send_message(chat_id=ADMIN_ID, text=info_msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        await update.message.forward(chat_id=ADMIN_ID)
        await update.message.reply_text("✅ رسید ارسال شد. منتظر تایید مدیر باشید.")
        return

    text = update.message.text
    
    if context.user_data.get('awaiting_ai'):
        msg = await update.message.reply_text("🧠 در حال فکر...")
        try:
            response = requests.get(f"{AI_API_URL}{text}", timeout=15)
            if response.status_code == 200: 
                await msg.edit_text(response.text)
                add_score(user.id, 2)
        except: await msg.edit_text("❌ خطا.")
        return

    if not text.startswith('http'):
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"💬 پیام از {user.first_name} (`{user.id}`):\n\n{text}", parse_mode='Markdown')
        await update.message.reply_text("✅ پیام ارسال شد.")
        return

    # 👇 شرط مدیر که محدودیت نداشته باشه
    if user.id != ADMIN_ID and not status['is_vip'] and status['downloads'] >= 3 + status.get('bonus', 0):
        await update.message.reply_text(get_text('limit', lang), parse_mode='Markdown')
        return

    msg = await update.message.reply_text(get_text('processing', lang))
    
    # ۱. چک کردن لینک‌های تلگرام
    if 't.me/' in text:
        await msg.edit_text("🔗 این لینک مربوط به تلگرام است.\nلطفاً برای دانلود، لینک مستقیم ویدیو یا فایل را بفرستید.")
        return

    # ۲. چک کردن فایل‌های PDF، عکس، زیپ
    if text.lower().endswith(('.pdf', '.jpg', '.jpeg', '.png', '.zip', '.rar', '.apk')):
        await msg.edit_text("📥 در حال دانلود فایل...")
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            r = requests.get(text, headers=headers, stream=True, timeout=30)
            file_size = int(r.headers.get('content-length', 0))
            
            if file_size > 50 * 1024 * 1024:
                await msg.edit_text(f"📥 حجم فایل بیشتر از ۵۰ مگابایت است.\n\n👇 لینک مستقیم:\n{text}")
                return
            
            file_name = text.split('/')[-1]
            with open(file_name, 'wb') as f:
                for chunk in r.iter_content(1024*1024):
                    f.write(chunk)
            
            with open(file_name, 'rb') as f:
                await update.message.reply_document(document=f, caption="✅ فایل دانلود شد!", parse_mode='Markdown')
            
            os.remove(file_name)
            await msg.delete()
            
            increment_download(user.id)
            
        except Exception as e:
            await msg.edit_text(f"❌ خطا در دانلود فایل:\n`{str(e)[:100]}`", parse_mode='Markdown')
        return

    # ۳. دانلود ویدیو و موزیک با yt-dlp
    try:
        ydl_opts = {
            'quiet': True, 
            'no_warnings': True, 
            'extractor_args': {
                'youtube': {
                    'player_client': ['ios', 'android', 'tv', 'web']
                }
            }
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(text, download=False)
            best_url = None
            for f in reversed(info.get('formats', [])):
                if f.get('ext') == 'mp4' and f.get('url'):
                    best_url = f['url']
                    break
            file_size = info.get('filesize', 0) or info.get('filesize_approx', 0)
            
            if file_size and file_size < 50 * 1024 * 1024:
                await msg.edit_text("📤 دانلود...")
                ydl_opts_dl = {**ydl_opts, 'outtmpl': 'downloads/%(title)s.%(ext)s'}
                with yt_dlp.YoutubeDL(ydl_opts_dl) as ydl_dl:
                    info_dl = ydl_dl.extract_info(text, download=True)
                    filename = ydl_dl.prepare_filename(info_dl)
                    with open(filename, 'rb') as f:
                        await update.message.reply_video(video=f, caption="✅ دانلود شد!\n🌐 @Multimedia_Land_bot", parse_mode='Markdown')
                    os.remove(filename)
                    await msg.delete()
            else:
                direct_text = get_text('too_large', lang).format(best_url)
                await msg.edit_text(direct_text, parse_mode='Markdown')

        if not status['is_vip']: 
            increment_download(user.id)

    except Exception as e:
        await msg.edit_text(get_text('error', lang).format(str(e)[:100]), parse_mode='Markdown')

# ================= 👑 پنل ادمین (کامل) =================
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM users WHERE is_vip = 1")
    total_vips = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM payments WHERE status = 'Pending'")
    pending_payments = cursor.fetchone()[0]
    conn.close()
    text = (f"👑 **پنل مدیریت**\n\n"
            f"👥 کاربران: {total_users}\n"
            f"💎 VIP: {total_vips}\n"
            f"⏳ پرداخت‌های در انتظار: {pending_payments}\n\n"
            f"دستورات:\n"
            f"`/addvip [id]` - فعال‌سازی VIP\n"
            f"`/history [id]` - تاریخچه کاربر\n"
            f"`/broadcast [متن]` - پیام به همه\n"
            f"`/addpromo [کد] [درصد] [تعداد]` - ساخت کد تخفیف\n"
            f"`/stats` - آمار کلی\n"
            f"`/channel` - مدیریت کانال")
    await update.message.reply_text(text, parse_mode='Markdown')

async def stats_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM users WHERE is_vip = 1")
    total_vips = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM activity_logs WHERE action = 'دانلود موفق'")
    total_downloads = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM activity_logs WHERE action = 'چت با هوش مصنوعی'")
    total_ai = cursor.fetchone()[0]
    conn.close()
    text = (f"📊 **آمار زنده ربات**\n\n"
            f"👥 کل کاربران: {total_users}\n"
            f"💎 کاربران VIP: {total_vips}\n"
            f"📥 دانلودهای موفق: {total_downloads}\n"
            f"🤖 چت با هوش مصنوعی: {total_ai}")
    await update.message.reply_text(text, parse_mode='Markdown')

async def channel_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text(f"📢 کانال اجباری فعلی: `@{FORCE_JOIN_CHANNEL}`\n\nبرای تغییر، باید کد رو ویرایش کنی.", parse_mode='Markdown')

async def add_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        target_id = int(context.args[0])
        set_vip(target_id)
        await update.message.reply_text(f"✅ کاربر {target_id} VIP شد.")
    except: await update.message.reply_text("❌ فرمت: `/addvip 123456789`")

async def user_history_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        target_id = int(context.args[0])
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT action, details, timestamp FROM activity_logs WHERE user_id = ? ORDER BY id DESC LIMIT 20", (target_id,))
        logs = cursor.fetchall()
        conn.close()
        text = f"📜 **تاریخچه `{target_id}`:**\n\n"
        for log in logs: text += f"🔸 {log[0]} ({log[2]})\n"
        await update.message.reply_text(text, parse_mode='Markdown')
    except: await update.message.reply_text("❌ فرمت: `/history 123456789`")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    msg_text = ' '.join(context.args)
    if not msg_text: return
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    conn.close()
    count = 0
    for u in users:
        try:
            await context.bot.send_message(chat_id=u[0], text=msg_text)
            count += 1
        except: pass
    await update.message.reply_text(f"✅ برای {count} نفر ارسال شد.")

async def add_promo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        code = context.args[0].upper()
        discount = int(context.args[1])
        max_uses = int(context.args[2])
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO promos (code, discount, max_uses, uses) VALUES (?, ?, ?, 0)", (code, discount, max_uses))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"✅ کد `{code}` ساخته شد.")
    except: await update.message.reply_text("❌ فرمت: `/addpromo OFF50 50 100`")

async def lang_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = []
    for code, name in LANGUAGES:
        keyboard.append([InlineKeyboardButton(name, callback_data=f"set_lang_{code}")])
    await update.message.reply_text("🌐 لطفاً زبان خود را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))

# ================= ⚡ دکمه تایید VIP =================
async def approve_vip_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID: return
    
    user_id = int(query.data.split('_')[2])
    set_vip(user_id)
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE payments SET status = 'Approved' WHERE user_id = ? AND status = 'Pending'", (user_id,))
    conn.commit()
    conn.close()
    
    await query.edit_message_text(f"✅ کاربر `{user_id}` با موفقیت VIP شد.", parse_mode='Markdown')
    await context.bot.send_message(chat_id=user_id, text="🎉 تبریک! اشتراک VIP شما فعال شد. الان می‌تونید نامحدود دانلود کنید.")

def main():
    init_db()
    threading.Thread(target=run_dummy_server, daemon=True).start()
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("lang", lang_command))
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CommandHandler("stats", stats_panel))
    application.add_handler(CommandHandler("channel", channel_panel))
    application.add_handler(CommandHandler("addvip", add_vip))
    application.add_handler(CommandHandler("history", user_history_admin))
    application.add_handler(CommandHandler("broadcast", broadcast))
    application.add_handler(CommandHandler("addpromo", add_promo))
    application.add_handler(CallbackQueryHandler(approve_vip_callback, pattern='^approve_vip_'))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT | filters.CONTACT | filters.PHOTO, handle_message))
    print("🚀 Bot is running...")
    application.run_polling()

if __name__ == '__main__':
    main()
