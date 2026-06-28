# -*- coding: utf-8 -*-
import telebot
import requests
import json
import sqlite3
import random
import string
import os
import sys
import time
import threading
import jwt
from datetime import datetime
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

# ==========================================
#              تنظیمات و متغیرها
# ==========================================
def load_config():
    global config
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)
    except FileNotFoundError:
        config = {
            "bot_token": "", 
            "super_admin": 0, 
            "panel_url": "", 
            "marzban_admin_username": "", 
            "marzban_admin_password": "", 
            "card_number": "", 
            "card_holder": "", 
            "auto_backup_hours": 0,
            "github_url": "https://github.com/yourusername/yourrepo"
        }

load_config()
bot = telebot.TeleBot(config.get("bot_token", ""))
SUPER_ADMIN = config.get("super_admin", 0)

def save_config(new_key, new_value):
    global config
    config[new_key] = new_value
    with open("config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

# ==========================================
#          سیستم کلیدها و لایسنس
# ==========================================
PRIVATE_KEY_FILE = "private_key.pem"
PUBLIC_KEY_FILE = "public_key.pem"

def load_or_generate_keys():
    global PRIVATE_KEY
    if not os.path.exists(PRIVATE_KEY_FILE):
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_key = private_key.public_key()
        
        with open(PRIVATE_KEY_FILE, "wb") as f:
            f.write(private_key.private_bytes(encoding=serialization.Encoding.PEM, format=serialization.PrivateFormat.PKCS8, encryption_algorithm=serialization.NoEncryption()))
        with open(PUBLIC_KEY_FILE, "wb") as f:
            f.write(public_key.public_bytes(encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo))
            
    with open(PRIVATE_KEY_FILE, "rb") as f:
        PRIVATE_KEY = f.read()

load_or_generate_keys()

def generate_license(user_id, days_valid):
    import datetime as dt
    expiration_date = dt.datetime.utcnow() + dt.timedelta(days=days_valid)
    payload = {"admin_id": user_id, "exp": expiration_date, "type": "pasargad_panel"}
    return jwt.encode(payload, PRIVATE_KEY, algorithm="RS256")

# ==========================================
#                دیتابیس
# ==========================================
def get_db_connection():
    conn = sqlite3.connect("pasargad_db.sqlite", check_same_thread=False, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    try:
        db = get_db_connection()
        c = db.cursor()
        
        c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 0, is_admin INTEGER DEFAULT 0)''')
        c.execute('''CREATE TABLE IF NOT EXISTS packages (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, volume INTEGER, price INTEGER)''')
        c.execute('''CREATE TABLE IF NOT EXISTS license_packages (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, days INTEGER, price INTEGER)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_services (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT, password TEXT, volume_total INTEGER)''')
        c.execute('''CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, date TIMESTAMP, description TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_states (user_id INTEGER PRIMARY KEY, state_key TEXT, state_data TEXT)''')
                     
        db.commit()
        db.close()
    except Exception as e:
        print(f"Error initializing DB: {e}")

def set_user_state(user_id, key, data=""):
    try:
        db = get_db_connection()
        c = db.cursor()
        c.execute("REPLACE INTO user_states (user_id, state_key, state_data) VALUES (?, ?, ?)", (user_id, key, json.dumps(data)))
        db.commit()
        db.close()
    except Exception as e: print(f"Error setting user state: {e}")

def get_user_state(user_id, key):
    try:
        db = get_db_connection()
        c = db.cursor()
        c.execute("SELECT state_data FROM user_states WHERE user_id = ? AND state_key = ?", (user_id, key))
        res = c.fetchone()
        db.close()
        if res: return json.loads(res['state_data'])
    except Exception as e: print(f"Error getting user state: {e}")
    return None

def clear_user_state(user_id):
    try:
        db = get_db_connection()
        c = db.cursor()
        c.execute("DELETE FROM user_states WHERE user_id = ?", (user_id,))
        db.commit()
        db.close()
    except Exception as e: print(f"Error clearing user state: {e}")

def is_user_admin(user_id):
    if user_id == SUPER_ADMIN: return True
    try:
        db = get_db_connection()
        c = db.cursor()
        c.execute("SELECT is_admin FROM users WHERE user_id = ?", (user_id,))
        res = c.fetchone()
        db.close()
        return res['is_admin'] if res else False
    except: return False

def get_balance(user_id):
    try:
        db = get_db_connection()
        c = db.cursor()
        c.execute("INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, 0)", (user_id,))
        db.commit()
        c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        res = c.fetchone()
        db.close()
        return res['balance'] if res else 0
    except: return 0

# ==========================================
#          ارتباط با API پاسارگاد
# ==========================================
def generate_random_password():
    uppercase_letters = random.choices(string.ascii_uppercase, k=2)
    special_chars = random.choices("@#$%^&*!?", k=2)
    lowercase_letters = random.choices(string.ascii_lowercase, k=4)
    digits = random.choices(string.digits, k=4)
    all_chars = uppercase_letters + special_chars + lowercase_letters + digits
    random.shuffle(all_chars)
    return ''.join(all_chars)

def get_panel_token():
    url = f"{config.get('panel_url', '')}/admin/token"
    payload = {"username": config.get("marzban_admin_username", ""), "password": config.get("marzban_admin_password", "")}
    try:
        response = requests.post(url, data=payload, timeout=10)
        return response.json().get("access_token") if response.status_code == 200 else None
    except: return None

def create_panel_admin_reseller(username, password, data_limit_bytes):
    token = get_panel_token()
    if not token: return 401, "عدم دریافت توکن از پاسارگاد"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"username": username, "password": password, "role": "reseller", "is_sudo": False, "status": "active", "data_limit": data_limit_bytes, "system_data_limit": data_limit_bytes, "admin_data_limit": data_limit_bytes, "admin_inbounds": []}
    try:
        response = requests.post(f"{config['panel_url']}/admin", json=payload, headers=headers, timeout=10)
        if response.status_code == 422 and "role_id" in response.text:
            payload["role_id"] = 3
            response = requests.post(f"{config['panel_url']}/admin", json=payload, headers=headers, timeout=10)
        return response.status_code, response.text
    except Exception as e: return 500, str(e)

def get_panel_admin_info(username):
    token = get_panel_token()
    if not token: return None
    headers = {"Authorization": f"Bearer {token}"}
    try:
        response = requests.get(f"{config['panel_url']}/admin/{username}", headers=headers, timeout=10)
        return response.json() if response.status_code == 200 else None
    except: return None

def update_panel_admin_limit(username, new_limit_bytes):
    token = get_panel_token()
    if not token: return False
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"data_limit": new_limit_bytes, "system_data_limit": new_limit_bytes, "admin_data_limit": new_limit_bytes}
    try:
        response = requests.put(f"{config['panel_url']}/admin/{username}", json=payload, headers=headers, timeout=10)
        return response.status_code == 200
    except: return False

# ==========================================
#               بکاپ خودکار
# ==========================================
def create_backup():
    db = get_db_connection()
    data = {"users": [], "packages": [], "license_packages": [], "user_services": [], "payments": []}
    try:
        c = db.cursor()
        c.execute("SELECT * FROM users"); data["users"] = [dict(row) for row in c.fetchall()]
        c.execute("SELECT * FROM packages"); data["packages"] = [dict(row) for row in c.fetchall()]
        c.execute("SELECT * FROM license_packages"); data["license_packages"] = [dict(row) for row in c.fetchall()]
        c.execute("SELECT * FROM user_services"); data["user_services"] = [dict(row) for row in c.fetchall()]
        c.execute("SELECT * FROM payments"); data["payments"] = [dict(row) for row in c.fetchall()]
    except Exception as e: print(f"Error creating backup: {e}")
    finally: db.close()
    
    def default_serializer(obj):
        if isinstance(obj, datetime): return obj.isoformat()
        raise TypeError("Type not serializable")

    with open("backup.json", "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=4, default=default_serializer)
    return "backup.json"

def auto_backup_loop():
    while True:
        time.sleep(3600)
        hours = config.get("auto_backup_hours", 0)
        if hours > 0:
            last_backup = config.get("last_backup_time", 0)
            now = time.time()
            if now - last_backup >= (hours * 3600):
                try:
                    file_path = create_backup()
                    with open(file_path, "rb") as f: bot.send_document(SUPER_ADMIN, f, caption=f"⏱ فایل بکاپ خودکار دیتابیس")
                    save_config("last_backup_time", now)
                except: pass

# ==========================================
#                 منوها
# ==========================================
def main_menu(user_id):
    markup = telebot.types.InlineKeyboardMarkup()
    markup.row(telebot.types.InlineKeyboardButton("🛒 خرید پنل نمایندگی 🛒", callback_data="buy_package"))
    markup.row(
        telebot.types.InlineKeyboardButton("👤 کیف پول", callback_data="wallet_menu"),
        telebot.types.InlineKeyboardButton("🌐 سرویس‌های من", callback_data="my_services")
    )
    markup.row(telebot.types.InlineKeyboardButton("🔑 خرید لایسنس ربات", callback_data="buy_license_menu"))
    markup.row(telebot.types.InlineKeyboardButton("🎧 ارتباط با پشتیبانی", callback_data="support_start"))
    if is_user_admin(user_id):
        markup.row(telebot.types.InlineKeyboardButton("🛡 پنل مدیریت", callback_data="admin_panel"))
    return markup

# ==========================================
#               هندلرهای اصلی
# ==========================================
@bot.message_handler(commands=['start', 'restart'])
def send_welcome(message):
    get_balance(message.from_user.id)
    bot.reply_to(message, f"👋 به ربات پاسارگاد خوش آمدید.\n💰 موجودی شما: {get_balance(message.from_user.id):,} تومان", reply_markup=main_menu(message.from_user.id))

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id, chat_id, msg_id = call.from_user.id, call.message.chat.id, call.message.message_id

    if call.data == "back_main":
        bot.edit_message_text(f"👋 به منوی اصلی بازگشتید:\n💰 موجودی شما: {get_balance(user_id):,} تومان", chat_id, msg_id, reply_markup=main_menu(user_id))

    # ---------------- پنل مدیریت ----------------
    elif call.data == "admin_panel":
        if not is_user_admin(user_id): return
        markup = telebot.types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            telebot.types.InlineKeyboardButton("📦 پلن‌های نمایندگی", callback_data="adm_pkgs"),
            telebot.types.InlineKeyboardButton("🎫 لایسنس‌ها", callback_data="adm_lic_pkgs")
        )
        markup.add(
            telebot.types.InlineKeyboardButton("⚙️ تنظیمات سیستم", callback_data="adm_cfg"),
            telebot.types.InlineKeyboardButton("💳 شماره کارت", callback_data="adm_card")
        )
        markup.add(
            telebot.types.InlineKeyboardButton("👥 کاربران", callback_data="adm_users"),
            telebot.types.InlineKeyboardButton("📊 آمار", callback_data="adm_stats")
        )
        markup.add(
            telebot.types.InlineKeyboardButton("📢 پیام همگانی", callback_data="adm_broadcast"),
            telebot.types.InlineKeyboardButton("👥 مدیریت ادمین", callback_data="adm_admins")
        )
        markup.add(
            telebot.types.InlineKeyboardButton("💾 بکاپ فوری", callback_data="adm_backup"),
            telebot.types.InlineKeyboardButton("♻️ بازیابی", callback_data="adm_restore")
        )
        markup.add(
            telebot.types.InlineKeyboardButton("⏱ تنظیم بکاپ خودکار", callback_data="adm_autobackup"),
            telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")
        )
        bot.edit_message_text("🛡 **پنل مدیریت پاسارگاد**", chat_id, msg_id, parse_mode="Markdown", reply_markup=markup)

    # ---------------- مدیریت پکیج‌های لایسنس (ادمین) ----------------
    elif call.data == "adm_lic_pkgs":
        if not is_user_admin(user_id): return
        db = get_db_connection()
        c = db.cursor()
        c.execute("SELECT * FROM license_packages")
        pkgs = c.fetchall()
        db.close()
        markup = telebot.types.InlineKeyboardMarkup(row_width=1)
        markup.add(telebot.types.InlineKeyboardButton("➕ افزودن پلن لایسنس", callback_data="adm_add_lic_pkg"))
        for p in pkgs:
            markup.add(telebot.types.InlineKeyboardButton(f"🎫 {p['title']} ({p['days']} روز) - {p['price']:,}ت", callback_data=f"lic_mgr_{p['id']}"))
        markup.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel"))
        bot.edit_message_text("🎫 **مدیریت پلن‌های فروش لایسنس**", chat_id, msg_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "adm_add_lic_pkg":
        if not is_user_admin(user_id): return
        sent = bot.send_message(chat_id, "✏️ لطفاً **نام** پلن لایسنس (مثلا ۱ ماهه) را ارسال کنید:", parse_mode="Markdown")
        bot.register_next_step_handler(sent, process_add_lic_step1)

    elif call.data.startswith("lic_mgr_"):
        if not is_user_admin(user_id): return
        pkg_id = call.data.split("_")[2]
        markup = telebot.types.InlineKeyboardMarkup(row_width=2).add(
            telebot.types.InlineKeyboardButton("❌ حذف پلن", callback_data=f"lic_del_{pkg_id}"),
            telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="adm_lic_pkgs")
        )
        bot.edit_message_text("⚙️ **عملیات پلن لایسنس:**", chat_id, msg_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("lic_del_"):
        if not is_user_admin(user_id): return
        pkg_id = call.data.split("_")[2]
        db = get_db_connection()
        c = db.cursor()
        c.execute("DELETE FROM license_packages WHERE id = ?", (pkg_id,))
        db.commit(); db.close()
        bot.answer_callback_query(call.id, "✅ پلن لایسنس حذف شد.", show_alert=True)
        handle_callbacks(telebot.types.CallbackQuery(call.id, call.from_user, "adm_lic_pkgs", call.message))

    # ---------------- خرید لایسنس (کاربر) ----------------
    elif call.data == "buy_license_menu":
        db = get_db_connection()
        c = db.cursor()
        c.execute("SELECT * FROM license_packages")
        packages = c.fetchall()
        db.close()
        markup = telebot.types.InlineKeyboardMarkup(row_width=1)
        for pkg in packages:
            markup.add(telebot.types.InlineKeyboardButton(f"🔑 {pkg['title']} | {pkg['price']:,} تومان", callback_data=f"orderlic_{pkg['id']}"))
        markup.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_main"))
        bot.edit_message_text("🛒 *پلن‌های خرید لایسنس ربات:*", chat_id, msg_id, reply_markup=markup, parse_mode="Markdown")

    elif call.data.startswith("orderlic_"):
        pkg_id = call.data.split("_")[1]
        db = get_db_connection()
        c = db.cursor()
        c.execute("SELECT * FROM license_packages WHERE id = ?", (pkg_id,))
        pkg = c.fetchone()
        db.close()
        if pkg:
            if get_balance(user_id) < pkg['price']:
                markup = telebot.types.InlineKeyboardMarkup().add(
                    telebot.types.InlineKeyboardButton("💳 افزایش موجودی", callback_data="ask_amount"),
                    telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="buy_license_menu")
                )
                bot.edit_message_text(f"❌ موجودی کافی نیست!\n💰 موجودی: {get_balance(user_id):,} تومان", chat_id, msg_id, reply_markup=markup, parse_mode="Markdown")
                return

            bot.edit_message_text("⏳ در حال تولید لایسنس اختصاصی و کسر موجودی...", chat_id, msg_id)
            
            # تولید لایسنس برای آیدی کاربر خریدار
            license_key = generate_license(user_id, pkg['days'])
            
            db = get_db_connection()
            c = db.cursor()
            c.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (pkg['price'], user_id))
            c.execute("INSERT INTO payments (user_id, amount, date, description) VALUES (?, ?, ?, ?)", (user_id, pkg['price'], datetime.now(), f"خرید لایسنس ({pkg['title']})"))
            db.commit(); db.close()
            
            msg = f"🎉 **خرید لایسنس موفقیت‌آمیز بود!**\n\n"
            msg += f"اعتبار: {pkg['days']} روز\nاختصاصی برای آیدی: `{user_id}`\n\n"
            msg += f"🔑 **کد لایسنس شما:**\n`{license_key}`\n\n"
            msg += "⚠️ *این کد را کپی کرده و پس از نصب اسکریپت، آن را در ربات جدید خود استفاده کنید.*"
            
            # ایجاد دکمه لینک گیت‌هاب پس از خرید موفق
            github_url = config.get("github_url", "https://github.com/")
            delivery_markup = telebot.types.InlineKeyboardMarkup(row_width=1)
            delivery_markup.add(telebot.types.InlineKeyboardButton("📥 دریافت اسکریپت نصب ربات", url=github_url))
            delivery_markup.add(telebot.types.InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_main"))
            
            bot.send_message(chat_id, msg, parse_mode="Markdown", reply_markup=delivery_markup)

    # ---------------- تنظیمات سیستم ----------------
    elif call.data == "adm_cfg":
        if not is_user_admin(user_id): return
        markup = telebot.types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            telebot.types.InlineKeyboardButton("ویرایش آدرس پنل", callback_data="mcfg_url"),
            telebot.types.InlineKeyboardButton("ویرایش یوزرنیم پنل", callback_data="mcfg_user")
        )
        markup.add(
            telebot.types.InlineKeyboardButton("ویرایش پسورد پنل", callback_data="mcfg_pass"),
            telebot.types.InlineKeyboardButton("ویرایش لینک گیت‌هاب", callback_data="mcfg_github")
        )
        markup.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel"))
        
        msg = f"⚙️ **تنظیمات پنل و سیستم:**\n\n🌐 آدرس: `{config.get('panel_url', 'تنظیم نشده')}`\n👤 یوزر: `{config.get('marzban_admin_username', 'تنظیم نشده')}`\n🔑 پسورد: `{config.get('marzban_admin_password', 'تنظیم نشده')}`\n🔗 گیت‌هاب: `{config.get('github_url', 'تنظیم نشده')}`"
        bot.edit_message_text(msg, chat_id, msg_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("mcfg_"):
        if not is_user_admin(user_id): return
        action = call.data.split("_")[1]
        
        if action == "url": msg_text = "آدرس جدید پنل را بفرستید (همراه با /api):"
        elif action == "user": msg_text = "یوزرنیم جدید پنل را بفرستید:"
        elif action == "pass": msg_text = "پسورد جدید پنل را بفرستید:"
        elif action == "github": msg_text = "لینک جدید گیت‌هاب (شروع با https://) را بفرستید:"
        
        sent = bot.send_message(chat_id, f"✏️ {msg_text}")
        bot.register_next_step_handler(sent, process_edit_config, action)

    # ---------------- سایر بخش‌های قبلی مدیریت (بدون تغییر) ----------------
    elif call.data == "adm_autobackup":
        if not is_user_admin(user_id): return
        current_hours = config.get("auto_backup_hours", 0)
        status_text = f"هر {current_hours} ساعت" if current_hours > 0 else "غیرفعال ❌"
        msg = bot.send_message(chat_id, f"⏱ **وضعیت بکاپ خودکار:** {status_text}\n\nلطفاً برای تنظیم، فقط یک عدد (به ساعت) وارد کنید.\n*(برای غیرفعال سازی عدد 0 را ارسال کنید)*", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_autobackup)

    elif call.data == "adm_users":
        if not is_user_admin(user_id): return
        db = get_db_connection()
        c = db.cursor()
        c.execute("SELECT DISTINCT user_id FROM user_services")
        users = c.fetchall()
        db.close()
        markup = telebot.types.InlineKeyboardMarkup(row_width=2)
        for u in users: markup.add(telebot.types.InlineKeyboardButton(f"کاربر: {u['user_id']}", callback_data=f"admuser_{u['user_id']}"))
        markup.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel"))
        bot.edit_message_text("👥 **لیست کاربران دارای پنل نمایندگی:**", chat_id, msg_id, reply_markup=markup, parse_mode="Markdown")

    elif call.data.startswith("admuser_"):
        if not is_user_admin(user_id): return
        target_uid = call.data.split("_")[1]
        bal = get_balance(target_uid)
        markup = telebot.types.InlineKeyboardMarkup().add(
            telebot.types.InlineKeyboardButton("➕ افزایش موجودی", callback_data=f"baladd_{target_uid}"),
            telebot.types.InlineKeyboardButton("➖ کاهش موجودی", callback_data=f"balsub_{target_uid}")
        ).add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="adm_users"))
        bot.edit_message_text(f"👤 کاربر: `{target_uid}`\n💰 موجودی فعلی: {bal:,} تومان", chat_id, msg_id, reply_markup=markup, parse_mode="Markdown")

    elif call.data.startswith("baladd_") or call.data.startswith("balsub_"):
        if not is_user_admin(user_id): return
        action, target_uid = call.data.split("_")
        act_text = "افزایش" if action == "baladd" else "کاهش"
        msg = bot.send_message(chat_id, f"🔢 مبلغ مورد نظر برای **{act_text}** موجودی کاربر {target_uid} را به تومان وارد کنید:", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_manual_balance, target_uid, action)

    elif call.data == "adm_stats":
        if not is_user_admin(user_id): return
        db = get_db_connection()
        c = db.cursor()
        c.execute("SELECT COUNT(*) as count FROM users")
        user_count = c.fetchone()['count']
        c.execute("SELECT SUM(volume_total) as total_vol FROM user_services")
        res_vol = c.fetchone()['total_vol']
        total_vol = (res_vol or 0) / (1024**3)
        db.close()
        bot.answer_callback_query(call.id, f"👥 تعداد کاربران: {user_count}\n📊 کل حجم فروخته شده نمایندگی: {int(total_vol)} گیگابایت", show_alert=True)

    elif call.data == "adm_backup":
        if not is_user_admin(user_id): return
        bot.answer_callback_query(call.id, "⏳ در حال ساخت فایل پشتیبان...")
        file_path = create_backup()
        with open(file_path, "rb") as f: bot.send_document(chat_id, f, caption="✅ فایل بک‌آپ دیتابیس شما.")

    elif call.data == "adm_restore":
        if not is_user_admin(user_id): return
        msg = bot.send_message(chat_id, "⚠️ **هشدار ریستور:**\nلطفاً فایل `backup.json` را آپلود کنید تا اطلاعات جدید جایگزین شده و ربات ری‌استارت شود:", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_restore)

    elif call.data == "adm_broadcast":
        if not is_user_admin(user_id): return
        msg = bot.send_message(chat_id, "📢 متن پیام همگانی خود را بفرستید:")
        bot.register_next_step_handler(msg, process_broadcast)

    elif call.data == "adm_card":
        if not is_user_admin(user_id): return
        markup = telebot.types.InlineKeyboardMarkup().add(
            telebot.types.InlineKeyboardButton("✏️ ویرایش کارت", callback_data="cfg_card"),
            telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel")
        )
        bot.edit_message_text(f"💳 **کارت فعلی:**\nشماره: `{config.get('card_number', 'تنظیم نشده')}`\nبه نام: `{config.get('card_holder', 'تنظیم نشده')}`", chat_id, msg_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "cfg_card":
        if not is_user_admin(user_id): return
        sent = bot.send_message(chat_id, "✏️ شماره کارت و نام را با خط فاصله بفرستید.\nمثال: `6037999999999999-علی علوی`", parse_mode="Markdown")
        bot.register_next_step_handler(sent, process_edit_card)

    elif call.data == "adm_admins":
        if not is_user_admin(user_id): return
        markup = telebot.types.InlineKeyboardMarkup().add(
            telebot.types.InlineKeyboardButton("➕ افزودن ادمین", callback_data="adm_add_admin"),
            telebot.types.InlineKeyboardButton("➖ عزل ادمین", callback_data="adm_rem_admin"),
            telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel")
        )
        bot.edit_message_text("👥 **مدیریت ادمین‌های ربات**", chat_id, msg_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data in ["adm_add_admin", "adm_rem_admin"]:
        if not is_user_admin(user_id): return
        action = "add" if call.data == "adm_add_admin" else "remove"
        sent = bot.send_message(chat_id, "🔢 `User ID` عددی شخص را بفرستید:", parse_mode="Markdown")
        bot.register_next_step_handler(sent, process_manage_admin, action)

    # ---------------- مدیریت پلن‌های نمایندگی ----------------
    elif call.data == "adm_pkgs":
        if not is_user_admin(user_id): return
        db = get_db_connection()
        c = db.cursor()
        c.execute("SELECT * FROM packages")
        pkgs = c.fetchall()
        db.close()
        markup = telebot.types.InlineKeyboardMarkup(row_width=1)
        markup.add(telebot.types.InlineKeyboardButton("➕ افزودن پلن", callback_data="adm_add_pkg"))
        for p in pkgs:
            markup.add(telebot.types.InlineKeyboardButton(f"📦 {p['title']} ({p['volume']}G) - {p['price']:,}ت", callback_data=f"pkg_mgr_{p['id']}"))
        markup.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel"))
        bot.edit_message_text("📦 **مدیریت پلن‌های نمایندگی**", chat_id, msg_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "adm_add_pkg":
        if not is_user_admin(user_id): return
        sent = bot.send_message(chat_id, "✏️ لطفاً **نام** پلن جدید را ارسال کنید:", parse_mode="Markdown")
        bot.register_next_step_handler(sent, process_add_pkg_step1)

    elif call.data.startswith("pkg_mgr_"):
        if not is_user_admin(user_id): return
        pkg_id = call.data.split("_")[2]
        markup = telebot.types.InlineKeyboardMarkup(row_width=2).add(
            telebot.types.InlineKeyboardButton("✏️ ویرایش پلن", callback_data=f"pkg_edt_{pkg_id}"),
            telebot.types.InlineKeyboardButton("❌ حذف پلن", callback_data=f"pkg_del_{pkg_id}"),
            telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="adm_pkgs")
        )
        bot.edit_message_text("⚙️ **عملیات پلن نمایندگی:**", chat_id, msg_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("pkg_del_"):
        if not is_user_admin(user_id): return
        pkg_id = call.data.split("_")[2]
        db = get_db_connection()
        c = db.cursor()
        c.execute("DELETE FROM packages WHERE id = ?", (pkg_id,))
        db.commit()
        db.close()
        bot.answer_callback_query(call.id, "✅ پلن نمایندگی حذف شد.", show_alert=True)
        handle_callbacks(telebot.types.CallbackQuery(call.id, call.from_user, "adm_pkgs", call.message))

    elif call.data.startswith("pkg_edt_"):
        if not is_user_admin(user_id): return
        pkg_id = call.data.split("_")[2]
        sent = bot.send_message(chat_id, "✏️ لطفاً **نام جدید** پلن را ارسال کنید:", parse_mode="Markdown")
        bot.register_next_step_handler(sent, process_edit_pkg_step1, pkg_id)

    elif call.data == "support_start":
        msg = bot.send_message(chat_id, "🎧 لطفاً پیام، سوال یا مشکل خود را بنویسید:")
        bot.register_next_step_handler(msg, process_support_msg)

    elif call.data.startswith("replysup_"):
        if not is_user_admin(user_id): return
        target_uid = call.data.split("_")[1]
        msg = bot.send_message(chat_id, f"✏️ پاسخ خود را برای کاربر {target_uid} بنویسید:")
        bot.register_next_step_handler(msg, send_reply_to_user, target_uid)

    elif call.data == "wallet_menu":    
        markup = telebot.types.InlineKeyboardMarkup(row_width=2).add(
            telebot.types.InlineKeyboardButton("➕ افزایش موجودی", callback_data="ask_amount"),
            telebot.types.InlineKeyboardButton("📜 تاریخچه پرداخت‌ها", callback_data="pay_history")
        ).add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_main"))    
        bot.edit_message_text(f"👛 *مدیریت کیف پول*\n💰 موجودی: {get_balance(user_id):,} تومان", chat_id, msg_id, reply_markup=markup, parse_mode="Markdown")    

    elif call.data == "ask_amount":    
        msg = bot.send_message(chat_id, f"💳 به کارت زیر واریز نمایید:\n`{config.get('card_number')}`\nبه نام: {config.get('card_holder')}\n\n🔢 مبلغ واریزی به عدد (تومان) را بفرستید:", parse_mode="Markdown")    
        bot.register_next_step_handler(msg, process_amount)

    elif call.data == "pay_history":
        db = get_db_connection()
        c = db.cursor()
        c.execute("SELECT * FROM payments WHERE user_id = ? ORDER BY id DESC LIMIT 10", (user_id,))
        history = c.fetchall()
        db.close()
        
        markup = telebot.types.InlineKeyboardMarkup().add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="wallet_menu"))
        if not history:
            bot.edit_message_text("تراکنشی یافت نشد.", chat_id, msg_id, reply_markup=markup)
        else:
            msg_text = "📜 **تاریخچه ۱۰ پرداخت اخیر شما:**\n\n"
            for h in history:
                date_str = h['date'].split('.')[0] if isinstance(h['date'], str) else h['date'].strftime('%Y-%m-%d %H:%M')
                msg_text += f"💰 مبلغ: {h['amount']:,} تومان\n📅 زمان: {date_str}\n📝 بابت: {h['description']}\n〰️〰️〰️〰️\n"
            bot.edit_message_text(msg_text, chat_id, msg_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "buy_package":    
        db = get_db_connection()
        c = db.cursor()
        c.execute("SELECT * FROM packages")
        packages = c.fetchall()    
        db.close()    
        markup = telebot.types.InlineKeyboardMarkup(row_width=1)    
        for pkg in packages: markup.add(telebot.types.InlineKeyboardButton(f"📦 {pkg['title']} ({pkg['volume']}G) | {pkg['price']:,} تومان", callback_data=f"order_{pkg['id']}"))    
        markup.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_main"))    
        bot.edit_message_text("🛒 *پلن‌های پنل نمایندگی:*", chat_id, msg_id, reply_markup=markup, parse_mode="Markdown")    

    elif call.data.startswith("order_"):    
        pkg_id = call.data.split("_")[1]    
        db = get_db_connection()
        c = db.cursor()
        c.execute("SELECT * FROM packages WHERE id = ?", (pkg_id,))
        pkg = c.fetchone()    
        db.close()    
        if pkg:    
            if get_balance(user_id) < pkg['price']:    
                markup = telebot.types.InlineKeyboardMarkup().add(
                    telebot.types.InlineKeyboardButton("💳 افزایش موجودی", callback_data="ask_amount"),    
                    telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="buy_package")
                )    
                bot.edit_message_text(f"❌ موجودی کافی نیست!\n💰 موجودی: {get_balance(user_id):,} تومان", chat_id, msg_id, reply_markup=markup, parse_mode="Markdown")    
                return    

            bot.edit_message_text("⏳ در حال ساخت پنل نمایندگی پاسارگاد...", chat_id, msg_id)    
            user_nm, pwd = f"seller{random.randint(1000,9999)}", generate_random_password()    
            code, text = create_panel_admin_reseller(user_nm, pwd, int(pkg['volume']) * 1024**3)    
                
            if code in [200, 201]:    
                db = get_db_connection()
                c = db.cursor()
                c.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (pkg['price'], user_id))  
                c.execute("INSERT INTO user_services (user_id, username, password, volume_total) VALUES (?, ?, ?, ?)", (user_id, user_nm, pwd, int(pkg['volume']) * 1024**3))  
                c.execute("INSERT INTO payments (user_id, amount, date, description) VALUES (?, ?, ?, ?)", (user_id, pkg['price'], datetime.now(), f"خرید پنل نمایندگی ({pkg['title']})"))
                db.commit()
                db.close()
                msg = f"🎉 **پنل با موفقیت ساخته شد!**\n\n🌐 آدرس: {config['panel_url'].replace('/api', '')}\n👤 یوزر: `{user_nm}`\n🔑 رمز: `{pwd}`\n📊 حجم: {pkg['volume']} گیگ"    
                bot.send_message(chat_id, msg, parse_mode="Markdown", reply_markup=main_menu(user_id))    
            else:    
                bot.send_message(chat_id, "❌ خطایی در سرور پاسارگاد رخ داد.", reply_markup=main_menu(user_id))

    elif call.data == "my_services":  
        db = get_db_connection()
        c = db.cursor()
        c.execute("SELECT * FROM user_services WHERE user_id = ?", (user_id,))
        svcs = c.fetchall()  
        db.close()  
        markup = telebot.types.InlineKeyboardMarkup()  
        for s in svcs: markup.add(telebot.types.InlineKeyboardButton(f"🌐 {s['username']}", callback_data=f"svc_{s['id']}"))  
        markup.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_main"))  
        bot.edit_message_text("📱 *پنل‌های نمایندگی شما:*", chat_id, msg_id, reply_markup=markup, parse_mode="Markdown")  

    elif call.data.startswith("svc_"):  
        sid = call.data.split("_")[1]  
        db = get_db_connection()
        c = db.cursor()
        c.execute("SELECT * FROM user_services WHERE id = ?", (sid,))
        s = c.fetchone()  
        db.close()  
        if s:  
            info = get_panel_admin_info(s['username'])  
            init_vol = s['volume_total'] // 1024**3  
            rem_vol = round(max(0, info.get('data_limit', 0) - info.get('used_traffic', 0)) / 1024**3, 2) if info else "نامشخص"  
            msg = f"💎 **جزئیات پنل**\n\n👤 یوزر: `{s['username']}`\n🔑 رمز: `{s['password']}`\n📊 حجم کل: {init_vol} گیگ\n⏳ باقی‌مانده: {rem_vol} گیگ"  
            markup = telebot.types.InlineKeyboardMarkup().add(  
                telebot.types.InlineKeyboardButton("🔄 تمدید حجم", callback_data=f"renewmenu_{s['id']}"),  
                telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="my_services")  
            )  
            bot.edit_message_text(msg, chat_id, msg_id, parse_mode="Markdown", reply_markup=markup)  

    elif call.data.startswith("renewmenu_"):  
        svc_id = call.data.split("_")[1]  
        db = get_db_connection()
        c = db.cursor()
        c.execute("SELECT * FROM packages")
        packages = c.fetchall()  
        db.close()  
        markup = telebot.types.InlineKeyboardMarkup(row_width=1)  
        for p in packages: markup.add(telebot.types.InlineKeyboardButton(f"🚀 {p['title']} | +{p['volume']}G | {p['price']:,} ت", callback_data=f"renpkg_{svc_id}_{p['id']}"))  
        markup.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"svc_{svc_id}"))  
        bot.edit_message_text("⚡️ *پلن تمدید را انتخاب کنید:*", chat_id, msg_id, reply_markup=markup, parse_mode="Markdown")  

    elif call.data.startswith("renpkg_"):  
        _, svc_id, pkg_id = call.data.split("_")  
        set_user_state(user_id, "renew", {"svc_id": svc_id, "pkg_id": pkg_id})
        msg = bot.send_message(chat_id, f"💳 به کارت زیر واریز کنید:\n`{config.get('card_number')}`\n\n📸 عکس فیش را بفرستید:", parse_mode="Markdown")  
        bot.register_next_step_handler(msg, process_renew_receipt)

    elif call.data.startswith("cf_") or call.data.startswith("rj_"):
        if not is_user_admin(user_id): return
        action, uid, amt = call.data.split("_")
        if action == "cf":
            db = get_db_connection()
            c = db.cursor()
            c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (int(amt), int(uid)))
            c.execute("INSERT INTO payments (user_id, amount, date, description) VALUES (?, ?, ?, ?)", (int(uid), int(amt), datetime.now(), "افزایش موجودی - تایید فیش"))
            db.commit()
            db.close()
            bot.send_message(int(uid), f"🎉 واریزی {amt} تومانی تایید شد!")
            bot.edit_message_caption(f"✅ تایید شد\nمبلغ: {amt}", chat_id, msg_id)
        else:
            bot.send_message(int(uid), f"❌ واریزی {amt} تومانی رد شد.")
            bot.edit_message_caption(f"❌ رد شد\nمبلغ: {amt}", chat_id, msg_id)

    elif call.data.startswith("recf_") or call.data.startswith("rerj_"):
        if not is_user_admin(user_id): return
        action, svc_id, pkg_id = call.data.split("_")
        db = get_db_connection()
        c = db.cursor()
        c.execute("SELECT * FROM user_services WHERE id = ?", (svc_id,))
        svc = c.fetchone()
        c.execute("SELECT * FROM packages WHERE id = ?", (pkg_id,))
        pkg = c.fetchone()
        
        if action == "recf" and svc and pkg:
            info = get_panel_admin_info(svc['username'])
            cur_limit = info.get('data_limit', 0) if info else svc['volume_total']
            new_limit = cur_limit + (int(pkg['volume']) * 1024**3)
            if update_panel_admin_limit(svc['username'], new_limit):
                c.execute("UPDATE user_services SET volume_total = ? WHERE id = ?", (new_limit, svc_id))
                c.execute("INSERT INTO payments (user_id, amount, date, description) VALUES (?, ?, ?, ?)", (svc['user_id'], pkg['price'], datetime.now(), f"تمدید پنل {svc['username']} ({pkg['title']})"))
                db.commit()
                bot.send_message(svc['user_id'], f"✅ تمدید تایید و {pkg['volume']} گیگ اعمال شد!")
                bot.edit_message_caption("✅ تمدید انجام شد.", chat_id, msg_id)
            else: bot.edit_message_caption("❌ خطا در اتصال به پاسارگاد.", chat_id, msg_id)
        elif action == "rerj" and svc:
            bot.send_message(svc['user_id'], "❌ درخواست تمدید رد شد.")
            bot.edit_message_caption("❌ تمدید رد شد.", chat_id, msg_id)
        db.close()

# ==========================================
#             توابع پردازش (Next Step)
# ==========================================
def process_add_lic_step1(message):
    if not message.text: return bot.reply_to(message, "❌ ورودی نامعتبر.")
    pkg_name = message.text
    sent = bot.reply_to(message, f"✅ نام `{pkg_name}` ذخیره شد.\n\n🔢 حالا **مدت اعتبار** لایسنس (به روز - فقط عدد) را بفرستید:", parse_mode="Markdown")
    bot.register_next_step_handler(sent, process_add_lic_step2, pkg_name)

def process_add_lic_step2(message, pkg_name):
    if not message.text.isdigit(): return bot.reply_to(message, "❌ فقط عدد!")
    pkg_days = int(message.text)
    sent = bot.reply_to(message, f"✅ مدت `{pkg_days}` روز ذخیره شد.\n\n💰 حالا **قیمت** لایسنس (به تومان - فقط عدد) را بفرستید:", parse_mode="Markdown")
    bot.register_next_step_handler(sent, process_add_lic_step3, pkg_name, pkg_days)

def process_add_lic_step3(message, pkg_name, pkg_days):
    if not message.text.isdigit(): return bot.reply_to(message, "❌ فقط عدد!")
    pkg_price = int(message.text)
    try:
        db = get_db_connection()
        c = db.cursor()
        c.execute("INSERT INTO license_packages (title, days, price) VALUES (?, ?, ?)", (pkg_name, pkg_days, pkg_price))
        db.commit(); db.close()
        bot.reply_to(message, "✅ پلن لایسنس جدید با موفقیت اضافه شد.", reply_markup=main_menu(message.from_user.id))
    except Exception as e:
        bot.reply_to(message, f"❌ خطایی رخ داد: {e}", reply_markup=main_menu(message.from_user.id))

def process_autobackup(message):
    if not message.text.isdigit(): return bot.reply_to(message, "❌ لطفاً فقط عدد انگلیسی وارد کنید.")
    hours = int(message.text)
    save_config("auto_backup_hours", hours)
    if hours > 0:
        bot.reply_to(message, f"✅ عالی! فایل دیتابیس هر {hours} ساعت یک‌بار به صورت خودکار ارسال می‌شود.", reply_markup=main_menu(message.from_user.id))
    else:
        bot.reply_to(message, "✅ ارسال خودکار بکاپ غیرفعال شد.", reply_markup=main_menu(message.from_user.id))

def process_edit_pkg_step1(message, pkg_id):
    if not message.text: return bot.reply_to(message, "❌ ورودی نامعتبر.")
    pkg_name = message.text
    sent = bot.reply_to(message, f"✅ نام `{pkg_name}` ذخیره شد.\n\n🔢 حالا **حجم جدید** پلن (به گیگابایت - فقط عدد) را بفرستید:", parse_mode="Markdown")
    bot.register_next_step_handler(sent, process_edit_pkg_step2, pkg_id, pkg_name)

def process_edit_pkg_step2(message, pkg_id, pkg_name):
    if not message.text.isdigit(): return bot.reply_to(message, "❌ فقط عدد!")
    pkg_vol = int(message.text)
    sent = bot.reply_to(message, f"✅ حجم `{pkg_vol}` گیگ ذخیره شد.\n\n💰 حالا **قیمت جدید** پلن (تومان) را بفرستید:", parse_mode="Markdown")
    bot.register_next_step_handler(sent, process_edit_pkg_step3, pkg_id, pkg_name, pkg_vol)

def process_edit_pkg_step3(message, pkg_id, pkg_name, pkg_vol):
    if not message.text.isdigit(): return bot.reply_to(message, "❌ فقط عدد!")
    pkg_price = int(message.text)
    try:
        db = get_db_connection()
        c = db.cursor()
        c.execute("UPDATE packages SET title=?, volume=?, price=? WHERE id=?", (pkg_name, pkg_vol, pkg_price, pkg_id))
        db.commit(); db.close()
        bot.reply_to(message, "✅ پلن نمایندگی ویرایش شد.", reply_markup=main_menu(message.from_user.id))
    except Exception as e: bot.reply_to(message, f"❌ خطایی رخ داد: {e}", reply_markup=main_menu(message.from_user.id))

def process_add_pkg_step1(message):
    if not message.text: return bot.reply_to(message, "❌ ورودی نامعتبر.")
    pkg_name = message.text
    sent = bot.reply_to(message, f"✅ نام `{pkg_name}` ذخیره شد.\n\n🔢 حالا **حجم** پلن جدید (به گیگابایت - فقط عدد) را بفرستید:", parse_mode="Markdown")
    bot.register_next_step_handler(sent, process_add_pkg_step2, pkg_name)

def process_add_pkg_step2(message, pkg_name):
    if not message.text.isdigit(): return bot.reply_to(message, "❌ فقط عدد!")
    pkg_vol = int(message.text)
    sent = bot.reply_to(message, f"✅ حجم `{pkg_vol}` گیگ ذخیره شد.\n\n💰 حالا **قیمت** پلن (تومان) را بفرستید:", parse_mode="Markdown")
    bot.register_next_step_handler(sent, process_add_pkg_step3, pkg_name, pkg_vol)

def process_add_pkg_step3(message, pkg_name, pkg_vol):
    if not message.text.isdigit(): return bot.reply_to(message, "❌ فقط عدد!")
    pkg_price = int(message.text)
    try:
        db = get_db_connection()
        c = db.cursor()
        c.execute("INSERT INTO packages (title, volume, price) VALUES (?, ?, ?)", (pkg_name, pkg_vol, pkg_price))
        db.commit(); db.close()
        bot.reply_to(message, "✅ پلن نمایندگی جدید اضافه شد.", reply_markup=main_menu(message.from_user.id))
    except Exception as e: bot.reply_to(message, f"❌ خطایی رخ داد: {e}", reply_markup=main_menu(message.from_user.id))

def process_manual_balance(message, target_uid, action):
    if not message.text.isdigit(): 
        return bot.reply_to(message, "❌ لطفاً فقط عدد وارد کنید.")
    amt = int(message.text)
    try:
        db = get_db_connection()
        c = db.cursor()
        if action == "baladd": 
            c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amt, target_uid))
            desc = "افزایش موجودی توسط ادمین"
        else: 
            c.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amt, target_uid))
            desc = "کاهش موجودی توسط ادمین"
        c.execute("INSERT INTO payments (user_id, amount, date, description) VALUES (?, ?, ?, ?)", (target_uid, amt if action == "baladd" else -amt, datetime.now(), desc))
        db.commit()
        db.close()
        act_text = "افزایش" if action == "baladd" else "کاهش"
        bot.reply_to(message, f"✅ موجودی کاربر {target_uid} با موفقیت {amt} تومان {act_text} یافت.", reply_markup=main_menu(message.from_user.id))
        bot.send_message(target_uid, f"🔔 موجودی حساب شما مبلغ {amt} تومان توسط مدیریت {act_text} یافت.\n💰 موجودی فعلی: {get_balance(target_uid):,} تومان")
    except Exception as e: bot.reply_to(message, f"❌ خطا در عملیات: {e}")

def process_edit_config(message, action):
    if action == "url": save_config("panel_url", message.text)
    elif action == "user": save_config("marzban_admin_username", message.text)
    elif action == "pass": save_config("marzban_admin_password", message.text)
    elif action == "github": save_config("github_url", message.text)
    bot.reply_to(message, "✅ ذخیره شد.", reply_markup=main_menu(message.from_user.id))

def process_edit_card(message):
    try:
        parts = message.text.split("-")
        save_config("card_number", parts[0].strip())
        save_config("card_holder", parts[1].strip())
        bot.reply_to(message, "✅ ذخیره شد.", reply_markup=main_menu(message.from_user.id))
    except: bot.reply_to(message, "❌ فرمت اشتباه است.")

def process_manage_admin(message, action):
    if not message.text.isdigit(): return bot.reply_to(message, "❌ باید عدد باشد.")
    val = 1 if action == "add" else 0
    db = get_db_connection()
    c = db.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, balance, is_admin) VALUES (?, 0, ?)", (int(message.text), val))
    c.execute("UPDATE users SET is_admin = ? WHERE user_id = ?", (val, int(message.text)))
    db.commit()
    db.close()
    bot.reply_to(message, "✅ انجام شد.", reply_markup=main_menu(message.from_user.id))

def process_amount(message):
    if not message.text.isdigit(): return bot.reply_to(message, "❌ فقط عدد وارد کنید!")
    set_user_state(message.from_user.id, "deposit", message.text)
    msg = bot.reply_to(message, "📸 عکس فیش واریزی را بفرستید:")
    bot.register_next_step_handler(msg, process_receipt)

def process_receipt(message):
    if not message.photo: return bot.reply_to(message, "❌ فقط عکس!")
    amt = get_user_state(message.from_user.id, "deposit") or "0"
    clear_user_state(message.from_user.id)
    markup = telebot.types.InlineKeyboardMarkup().add(
        telebot.types.InlineKeyboardButton("✅ تایید", callback_data=f"cf_{message.from_user.id}_{amt}"),
        telebot.types.InlineKeyboardButton("❌ رد", callback_data=f"rj_{message.from_user.id}_{amt}")
    )
    bot.send_photo(SUPER_ADMIN, message.photo[-1].file_id, caption=f"💰 افزایش موجودی: {amt}\n👤 کاربر: {message.from_user.id}", reply_markup=markup)
    bot.reply_to(message, "✅ فیش ارسال شد.", reply_markup=main_menu(message.from_user.id))

def process_renew_receipt(message):
    if not message.photo: return bot.reply_to(message, "❌ فقط عکس!")
    data = get_user_state(message.from_user.id, "renew")
    clear_user_state(message.from_user.id)
    if not data: return bot.reply_to(message, "❌ خطا. مجدداً تلاش کنید.")
    db = get_db_connection()  
    c = db.cursor()
    c.execute("SELECT username FROM user_services WHERE id = ?", (data['svc_id'],))
    svc = c.fetchone()  
    c.execute("SELECT title, price FROM packages WHERE id = ?", (data['pkg_id'],))
    pkg = c.fetchone()  
    db.close()  
    if svc and pkg:
        markup = telebot.types.InlineKeyboardMarkup().add(
            telebot.types.InlineKeyboardButton("✅ تایید", callback_data=f"recf_{data['svc_id']}_{data['pkg_id']}"),
            telebot.types.InlineKeyboardButton("❌ رد", callback_data=f"rerj_{data['svc_id']}_{data['pkg_id']}")
        )
        bot.send_photo(SUPER_ADMIN, message.photo[-1].file_id, caption=f"🔄 تمدید پنل `{svc['username']}`\n💰 مبلغ: {pkg['price']}", reply_markup=markup)
        bot.reply_to(message, "✅ فیش تمدید ارسال شد.", reply_markup=main_menu(message.from_user.id))

def process_restore(message):
    if not message.document or not message.document.file_name.endswith('.json'): 
        return bot.reply_to(message, "❌ فایل نامعتبر است.")
    try:
        file_info = bot.get_file(message.document.file_id)
        data = json.loads(bot.download_file(file_info.file_path).decode('utf-8'))
        bot.reply_to(message, "⏳ در حال جایگزینی دیتابیس...")
        
        db = get_db_connection()
        c = db.cursor()
        for u in data.get("users", []): c.execute("REPLACE INTO users (user_id, balance, is_admin) VALUES (?, ?, ?)", (u['user_id'], u.get('balance',0), u.get('is_admin',0)))
        for p in data.get("packages", []): c.execute("REPLACE INTO packages (id, title, volume, price) VALUES (?, ?, ?, ?)", (p.get('id'), p.get('title'), p.get('volume'), p.get('price')))
        for p in data.get("license_packages", []): c.execute("REPLACE INTO license_packages (id, title, days, price) VALUES (?, ?, ?, ?)", (p.get('id'), p.get('title'), p.get('days'), p.get('price')))
        for s in data.get("user_services", []): c.execute("REPLACE INTO user_services (id, user_id, username, password, volume_total) VALUES (?, ?, ?, ?, ?)", (s.get('id'), s.get('user_id'), s.get('username'), s.get('password'), s.get('volume_total')))
        for py in data.get("payments", []): c.execute("REPLACE INTO payments (id, user_id, amount, date, description) VALUES (?, ?, ?, ?, ?)", (py.get('id'), py.get('user_id'), py.get('amount'), py.get('date'), py.get('description')))
        db.commit(); db.close()
            
        bot.send_message(message.chat.id, "✅ دیتابیس جایگزین شد! ربات اکنون ری‌استارت می‌شود...")
        os.execv(sys.executable, ['python'] + sys.argv)
    except Exception as e: bot.reply_to(message, f"❌ خطا هنگام ریستور دیتابیس: {e}")

def process_broadcast(message):
    db = get_db_connection()
    c = db.cursor()
    c.execute("SELECT user_id FROM users")
    users = c.fetchall()
    db.close()
    for u in users:
        try: bot.send_message(u['user_id'], f"📢 **پیام مدیریت:**\n\n{message.text}", parse_mode="Markdown")
        except: pass
    bot.reply_to(message, "✅ پیام ارسال شد.", reply_markup=main_menu(message.from_user.id))

def process_support_msg(message):
    markup = telebot.types.InlineKeyboardMarkup().add(telebot.types.InlineKeyboardButton("↩️ پاسخ به کاربر", callback_data=f"replysup_{message.from_user.id}"))
    bot.send_message(SUPER_ADMIN, f"📩 **پیام کاربر** `{message.from_user.id}`:\n\n{message.text}", parse_mode="Markdown", reply_markup=markup)
    bot.reply_to(message, "✅ پیام شما به پشتیبانی ارسال شد.", reply_markup=main_menu(message.from_user.id))

def send_reply_to_user(message, target_uid):
    try:
        bot.send_message(target_uid, f"🎧 **پاسخ پشتیبانی:**\n\n{message.text}", parse_mode="Markdown")
        bot.reply_to(message, "✅ پاسخ ارسال شد.")
    except Exception as e: bot.reply_to(message, f"❌ خطا: {e}")

# ==========================================
#                اجرای ربات
# ==========================================
bot.set_my_commands([
    telebot.types.BotCommand("/start", "🔄 اجرای مجدد ربات / برگشت به خانه"),
    telebot.types.BotCommand("/restart", "⚡️ رفرش و بارگذاری امکانات جدید")
])

print("⏳ Initializing Database and Security Keys...")
init_db()

threading.Thread(target=auto_backup_loop, daemon=True).start()

print("🚀 Pasargad Panel Bot Ultimate Is Active...")
bot.infinity_polling()
