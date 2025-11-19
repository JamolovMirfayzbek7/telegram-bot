import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from datetime import datetime, timedelta
import sqlite3
import asyncio

# Log sozlash
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

BOT_TOKEN = "8268206774:AAFiDMQFppE8Q64b2rIaGPl5iHGNVC5WY4M"

ADMIN_SECRET_CODE = "1234"   # Admin kirish kodi



# Database yaratish
def init_db():
    conn = sqlite3.connect('queue.db', check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            department_id INTEGER,
            client_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            queue_time TEXT NOT NULL,
            queue_number INTEGER,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            chat_id INTEGER,
            FOREIGN KEY (department_id) REFERENCES departments (id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            username TEXT
        )
    ''')

    # Boshlang'ich ma'lumotlar
    cursor.execute("SELECT COUNT(*) FROM departments")
    if cursor.fetchone()[0] == 0:
        departments = ['Terapiya', 'Stomatologiya', 'Laboratoriya', 'Rentgen', 'Shifokor maslahati']
        for dept in departments:
            cursor.execute("INSERT INTO departments (name) VALUES (?)", (dept,))

    cursor.execute("SELECT COUNT(*) FROM admins")
    if cursor.fetchone()[0] == 0:
        # O'z user ID ingizni qo'ying
        cursor.execute("INSERT INTO admins (user_id, username) VALUES (?, ?)", (6502927780, "admin"))

    conn.commit()
    conn.close()


init_db()


# Start komandasi
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🌟 Navbat olish", callback_data="get_queue")],
        [InlineKeyboardButton("📋 Mening navbatlarim", callback_data="my_queues")],
        [InlineKeyboardButton("🔧 Admin panel", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(
            "Assalomu alaykum! Navbat olish botiga xush kelibsiz.",
            reply_markup=reply_markup
        )
    else:
        await update.callback_query.edit_message_text(
            "Assalomu alaykum! Navbat olish botiga xush kelibsiz.",
            reply_markup=reply_markup
        )


# Bo'limlarni ko'rsatish
async def show_departments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    conn = sqlite3.connect('queue.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM departments")
    departments = cursor.fetchall()
    conn.close()

    keyboard = []
    for dept_id, dept_name in departments:
        keyboard.append([InlineKeyboardButton(dept_name, callback_data=f"dept_{dept_id}")])

    keyboard.append([InlineKeyboardButton("🔙 Orqaga", callback_data="main_menu")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "Qaysi bo'limga navbat olmoqchisiz?",
        reply_markup=reply_markup
    )


# Faqat band qilinmagan vaqtlarni ko'rsatish
def generate_available_times(dept_id):
    conn = sqlite3.connect('queue.db')
    cursor = conn.cursor()

    today = datetime.now().strftime("%Y-%m-%d")

    # Faqat ACTIVE navbatlarni olish
    cursor.execute('''
        SELECT queue_time FROM queue 
        WHERE department_id = ? AND DATE(queue_time) = ? AND status = 'active'
    ''', (dept_id, today))

    booked_times = [datetime.strptime(row[0], "%Y-%m-%d %H:%M") for row in cursor.fetchall()]

    conn.close()

    # Ish vaqti
    start_time = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)
    end_time = datetime.now().replace(hour=20, minute=0, second=0, microsecond=0)

    available_times = []
    current_time = start_time

    now = datetime.now()

    while current_time <= end_time:
        time_str = current_time.strftime("%Y-%m-%d %H:%M")

        # Bu vaqt bandmi?
        is_booked = any(bt == current_time for bt in booked_times)

        # ❗ Agar band bo'lsa ham, lekin vaqti o'tgan bo'lsa – bo'sh deb hisoblaymiz
        if is_booked and current_time <= now:
            current_time += timedelta(hours=1)
            continue

        # ❗ Kelajakda bo‘lsa va hali band bo'lmagan bo‘lsa
        if current_time > now and not is_booked:
            available_times.append(current_time.strftime("%H:%M"))

        current_time += timedelta(hours=1)

    return available_times


# Mavjud vaqtlarni ko'rsatish
async def show_available_times(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    dept_id = query.data.split("_")[1]
    context.user_data['selected_dept'] = dept_id

    available_times = generate_available_times(dept_id)

    if not available_times:
        await query.edit_message_text(
            "⚠️ Bugun barcha vaqtlar band qilingan. Iltimos, boshqa kun yoki bo'limni tanlang.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="get_queue")]])
        )
        return

    keyboard = []
    row = []
    for i, time_slot in enumerate(available_times):
        row.append(InlineKeyboardButton(time_slot, callback_data=f"time_{time_slot}"))
        if (i + 1) % 3 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("🔙 Orqaga", callback_data="get_queue")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    dept_name = get_department_name(dept_id)
    await query.edit_message_text(
        f"🏥 {dept_name} bo'limi uchun mavjud vaqtlar:\n\n"
        f"🟢 Yashil rangdagi vaqtlar band qilinmagan\n"
        f"Tanlang:",
        reply_markup=reply_markup
    )


# Mijoz ma'lumotlarini olish
async def get_client_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    selected_time = query.data.split("_")[1]
    context.user_data['selected_time'] = selected_time

    await query.edit_message_text(
        "Iltimos, ismingizni kiriting:"
    )
    context.user_data['waiting_for'] = 'name'


def get_queue_number(dept_id, selected_time):
    conn = sqlite3.connect('queue.db')
    cursor = conn.cursor()

    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute('''
        SELECT COUNT(*) FROM queue 
        WHERE department_id = ? AND DATE(queue_time) = ? AND status = 'active'
    ''', (dept_id, today))

    count = cursor.fetchone()[0]
    conn.close()

    return count + 1


def save_appointment(dept_id, client_name, phone, selected_time, queue_number, chat_id):
    conn = sqlite3.connect('queue.db')
    cursor = conn.cursor()

    full_time = f"{datetime.now().strftime('%Y-%m-%d')} {selected_time}"

    cursor.execute('''
        INSERT INTO queue (department_id, client_name, phone, queue_time, queue_number, status, chat_id)
        VALUES (?, ?, ?, ?, ?, 'active', ?)
    ''', (dept_id, client_name, phone, full_time, queue_number, chat_id))

    conn.commit()
    conn.close()


def get_department_name(dept_id):
    conn = sqlite3.connect('queue.db')
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM departments WHERE id = ?", (dept_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else "Noma'lum"


# Eslatma yuborish
async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    chat_id = job_data['chat_id']
    client_name = job_data['client_name']
    dept_name = job_data['dept_name']
    time = job_data['time']

    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"⏰ Diqqat {client_name}!\n\n"
                 f"Navbatingizga 5 daqiqa qoldi.\n"
                 f"🏥 Bo'lim: {dept_name}\n"
                 f"🕐 Vaqt: {time}\n\n"
                 f"Iltimos, o'z vaqtida kelishingizni so'raymiz."
        )
    except Exception as e:
        logging.error(f"Eslatma yuborishda xatolik: {e}")


# Vaqt o'tgach bandlikni olib tashlash
async def clear_expired_time(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    conn = sqlite3.connect('queue.db')
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE queue SET status = 'expired' 
        WHERE department_id = ? AND queue_time = ? AND status = 'active'
    ''', (job_data['dept_id'], job_data['time']))

    conn.commit()
    conn.close()

    logging.info(f"Vaqt tugadi: {job_data['time']}")


# Mijoz ma'lumotlarini qayta ishlash
async def process_client_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1) Admin kod kiritish holatini birinchi tekshiramiz
    if context.user_data.get("admin_login"):
        kod = update.message.text.strip()

        if kod == ADMIN_SECRET_CODE:
            # kod to'g'ri — lekin shu user admin jadvalidami, tekshiramiz
            if is_admin(update.effective_user.id):
                context.user_data.pop("admin_login", None)
                await update.message.reply_text("🔓 Kod tasdiqlandi! Admin panelga xush kelibsiz.")
                # admin_panel() message orqali chaqiriladi — u message holatini ham qamrab oladi
                await admin_panel(update, context)
            else:
                context.user_data.pop("admin_login", None)
                await update.message.reply_text("❌ Siz admin emassiz yoki admin ro'yxatda yo'q.")
        else:
            await update.message.reply_text("❌ Kod noto‘g‘ri! Qayta kiriting:")

        return  # boshqa ishlovlar bajarilmasin

    # 2) Adminga kiritish (bo'lim va admin qo'shish) kabi boshqa waiting_for holatlari
    if context.user_data.get('waiting_for') == 'new_department':
        dept_name = update.message.text.strip()
        conn = sqlite3.connect('queue.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO departments (name) VALUES (?)", (dept_name,))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"✅ '{dept_name}' bo'limi muvaffaqiyatli qo'shildi!")
        context.user_data.clear()
        return

    if context.user_data.get('waiting_for') == 'new_admin':
        try:
            user_id = int(update.message.text.strip())
            conn = sqlite3.connect('queue.db')
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (user_id,))
            conn.commit()
            conn.close()
            await update.message.reply_text(f"✅ Yangi admin (ID: {user_id}) muvaffaqiyatli qo'shildi!")
        except ValueError:
            await update.message.reply_text("❌ Noto'g'ri user ID formati! Faqat raqam kiriting.")
        context.user_data.clear()
        return

    # 3) Mijozdan ism va telefon olish ketma-ketligi
    if context.user_data.get('waiting_for') == 'name':
        context.user_data['client_name'] = update.message.text.strip()
        context.user_data['waiting_for'] = 'phone'
        await update.message.reply_text("Iltimos, telefon raqamingizni kiriting:\n\nMisol: +998901234567")
        return

    if context.user_data.get('waiting_for') == 'phone':
        phone = update.message.text.strip()
        dept_id = context.user_data.get('selected_dept')
        client_name = context.user_data.get('client_name')
        selected_time = context.user_data.get('selected_time')
        chat_id = update.effective_chat.id

        if not (dept_id and client_name and selected_time):
            await update.message.reply_text("❌ Xatolik: tanlangan bo'lim yoki vaqt topilmadi. Iltimos, boshidan boshlang.")
            context.user_data.clear()
            return

        queue_number = get_queue_number(dept_id, selected_time)
        save_appointment(dept_id, client_name, phone, selected_time, queue_number, chat_id)
        await notify_admins(context, dept_id, client_name, phone, selected_time, queue_number)

        department_name = get_department_name(dept_id)
        await update.message.reply_text(
            f"✅ Siz muvaffaqiyatli navbatga yozildingiz!\n\n"
            f"📋 Ma'lumotlar:\n"
            f"👤 Ism: {client_name}\n"
            f"📞 Telefon: {phone}\n"
            f"🏥 Bo'lim: {department_name}\n"
            f"🕐 Vaqt: {selected_time}\n"
            f"🔢 Navbat raqami: {queue_number}\n\n"
            f"Navbatingiz kelishiga 5 daqiqa qolganda sizga eslatma yuboriladi."
        )

        # Joblarni qo'shish (eslatma va expire) — sizning avvalgi kodga mos
        appointment_datetime = datetime.strptime(f"{datetime.now().strftime('%Y-%m-%d')} {selected_time}",
                                                 "%Y-%m-%d %H:%M")
        reminder_time = appointment_datetime - timedelta(minutes=5)
        if reminder_time > datetime.now():
            context.job_queue.run_once(
                send_reminder,
                reminder_time - datetime.now(),
                data={
                    'chat_id': chat_id,
                    'client_name': client_name,
                    'dept_name': department_name,
                    'time': selected_time
                }
            )

        expire_time = appointment_datetime + timedelta(minutes=10)
        if expire_time > datetime.now():
            context.job_queue.run_once(
                clear_expired_time,
                expire_time - datetime.now(),
                data={
                    'dept_id': dept_id,
                    'time': f"{datetime.now().strftime('%Y-%m-%d')} {selected_time}"
                }
            )

        keyboard = [
            [InlineKeyboardButton("❌ Navbatni bekor qilish", callback_data=f"cancel_{dept_id}_{selected_time}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Agar navbatni bekor qilmoqchi bo'lsangiz quyidagi tugmani bosing:", reply_markup=reply_markup)

        context.user_data.clear()
        return

    # Agar yuqoridagi holatlardan hech biri bo'lmasa — hech narsa qilmaymiz
    # yoki foydalanuvchiga asosiy menyuni taklif qilish mumkin
    await update.message.reply_text("Iltimos, menyudan kerakli tugmani tanlang yoki /start buyrug'ini bering.")


# adminni kodi bilan tekshiradigan funksiya
async def process_admin_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Agar kodni tekshirish rejimi bo'lmasa, boshqa joyga o'tkazamiz
    if context.user_data.get('waiting_for') != 'admin_login_code':
        return False

    kiritilgan_kod = update.message.text

    if kiritilgan_kod == ADMIN_SECRET_CODE:
        # Kod to'g'ri – admin panelga yo'naltiramiz
        context.user_data.pop('waiting_for', None)
        await update.message.reply_text("🔓 Kod tasdiqlandi!")
        # Admin menyusini ochamiz
        fake_update = Update(update.update_id, callback_query=None)
        await admin_panel(update, context)
    else:
        await update.message.reply_text("❌ Noto'g'ri kod! Yana urinib ko'ring.")

    return True



# Navbatni bekor qilish
async def cancel_appointment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data_parts = query.data.split("_")
    dept_id = data_parts[1]
    time = data_parts[2]
    chat_id = query.message.chat_id

    full_time = f"{datetime.now().strftime('%Y-%m-%d')} {time}"

    conn = sqlite3.connect('queue.db')
    cursor = conn.cursor()

    # Navbatni bekor qilish
    cursor.execute('''
        UPDATE queue SET status = 'cancelled' 
        WHERE department_id = ? AND queue_time = ? AND chat_id = ? AND status = 'active'
    ''', (dept_id, full_time, chat_id))

    affected_rows = cursor.rowcount
    conn.commit()
    conn.close()

    if affected_rows > 0:
        await query.edit_message_text(
            "✅ Sizning navbatingiz muvaffaqiyatli bekor qilindi.\n\n"
            "Boshqa vaqtda navbat olishingiz mumkin."
        )

        # Adminlarga bekor qilinganligi haqida xabar berish
        await notify_cancellation(context, dept_id, time, chat_id)
    else:
        await query.edit_message_text(
            "❌ Navbatni bekor qilishda xatolik yuz berdi. "
            "Iltimos, keyinroq urunib ko'ring yoki admin bilan bog'laning."
        )


# Mening navbatlarim
async def show_my_queues(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat_id

    conn = sqlite3.connect('queue.db')
    cursor = conn.cursor()

    cursor.execute('''
        SELECT d.name, q.client_name, q.queue_time, q.queue_number, q.status
        FROM queue q 
        JOIN departments d ON q.department_id = d.id 
        WHERE q.chat_id = ? AND DATE(q.queue_time) >= DATE('now')
        ORDER BY q.queue_time
    ''', (chat_id,))

    queues = cursor.fetchall()
    conn.close()

    if not queues:
        text = "📭 Sizda hozircha faol navbatlar yo'q."
    else:
        text = "📋 Mening navbatlarim:\n\n"
        for dept_name, client_name, queue_time, queue_num, status in queues:
            status_icon = "🟢" if status == 'active' else "🔴"
            status_text = "Faol" if status == 'active' else "Bekor qilingan"

            text += f"{status_icon} {dept_name}\n"
            text += f"👤 {client_name}\n"
            text += f"🕐 {queue_time}\n"
            text += f"🔢 {queue_num} - {status_text}\n"
            text += "─" * 30 + "\n"

    keyboard = [[InlineKeyboardButton("🔙 Asosiy menyu", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text, reply_markup=reply_markup)


async def notify_admins(context: ContextTypes.DEFAULT_TYPE, dept_id, client_name, phone, time, queue_num):
    conn = sqlite3.connect('queue.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM admins")
    admins = cursor.fetchall()
    conn.close()

    dept_name = get_department_name(dept_id)
    message = (
        "📋 Yangi navbat!\n\n"
        f"🏥 Bo'lim: {dept_name}\n"
        f"👤 Mijoz: {client_name}\n"
        f"📞 Telefon: {phone}\n"
        f"🕐 Vaqt: {time}\n"
        f"🔢 Navbat raqami: {queue_num}\n"
        f"📅 Sana: {datetime.now().strftime('%Y-%m-%d')}"
    )

    for admin in admins:
        try:
            await context.bot.send_message(chat_id=admin[0], text=message)
        except Exception as e:
            logging.error(f"Adminga xabar yuborishda xatolik: {e}")


async def notify_cancellation(context: ContextTypes.DEFAULT_TYPE, dept_id, time, chat_id):
    conn = sqlite3.connect('queue.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM admins")
    admins = cursor.fetchall()
    conn.close()

    dept_name = get_department_name(dept_id)
    message = (
        "❌ Navbat bekor qilindi!\n\n"
        f"🏥 Bo'lim: {dept_name}\n"
        f"🕐 Vaqt: {time}\n"
        f"📅 Sana: {datetime.now().strftime('%Y-%m-%d')}\n"
        f"👤 User ID: {chat_id}"
    )

    for admin in admins:
        try:
            await context.bot.send_message(chat_id=admin[0], text=message)
        except Exception as e:
            logging.error(f"Adminga bekor qilish xabarini yuborishda xatolik: {e}")


# # Admin inputni qayta ishlash
# async def process_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     if 'waiting_for' not in context.user_data:
#         return
#
#     if context.user_data['waiting_for'] == 'new_department':
#         dept_name = update.message.text
#
#         conn = sqlite3.connect('queue.db')
#         cursor = conn.cursor()
#         cursor.execute("INSERT INTO departments (name) VALUES (?)", (dept_name,))
#         conn.commit()
#         conn.close()
#
#         await update.message.reply_text(f"✅ '{dept_name}' bo'limi muvaffaqiyatli qo'shildi!")
#         context.user_data.clear()
#
#     elif context.user_data['waiting_for'] == 'new_admin':
#         try:
#             user_id = int(update.message.text)
#
#             conn = sqlite3.connect('queue.db')
#             cursor = conn.cursor()
#             cursor.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (user_id,))
#             conn.commit()
#             conn.close()
#
#             await update.message.reply_text(f"✅ Yangi admin (ID: {user_id}) muvaffaqiyatli qo'shildi!")
#         except ValueError:
#             await update.message.reply_text("❌ Noto'g'ri user ID formati! Faqat raqam kiriting.")
#
#         context.user_data.clear()


def is_admin(user_id):
    conn = sqlite3.connect('queue.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM admins WHERE user_id = ?", (user_id,))
    count = cursor.fetchone()[0]
    conn.close()
    return count > 0


# Admin panel
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Admin bo'lish huquqini tekshirish (foydalanuvchi ID asosida)
    user_id = update.effective_user.id if update.effective_user else None
    if not is_admin(user_id):
        # agar callback orqali kelgan bo'lsa -> edit_message, aks holda oddiy reply
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.message.edit_text("❌ Sizda admin huquqi yo'q!")
        else:
            await update.message.reply_text("❌ Sizda admin huquqi yo'q!")
        return

    # Adminga ko'rsatiladigan tugmalar
    keyboard = [
        [InlineKeyboardButton("📊 Bugungi navbatlar", callback_data="view_today_queues")],
        [InlineKeyboardButton("➕ Bo'lim qo'shish", callback_data="add_department")],
        [InlineKeyboardButton("👥 Admin qo'shish", callback_data="add_admin")],
        [InlineKeyboardButton("🔙 Asosiy menyu", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Agar callback orqali chaqirilgan bo'lsa -> edit_message yoki yangi xabar
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.edit_text("🔧 Admin paneliga xush kelibsiz:", reply_markup=reply_markup)
    else:
        await update.message.reply_text("🔧 Admin paneliga xush kelibsiz:", reply_markup=reply_markup)


# Bugungi navbatlarni ko'rish
async def view_today_queues(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    conn = sqlite3.connect('queue.db')
    cursor = conn.cursor()

    cursor.execute('''
        SELECT d.name, q.client_name, q.phone, q.queue_time, q.queue_number, q.status
        FROM queue q 
        JOIN departments d ON q.department_id = d.id 
        WHERE DATE(q.queue_time) = DATE('now') 
        ORDER BY q.queue_time
    ''')

    queues = cursor.fetchall()
    conn.close()

    if not queues:
        text = "📊 Bugun hech qanday navbat yo'q."
    else:
        text = "📊 Bugungi navbatlar:\n\n"
        for dept_name, client_name, phone, queue_time, queue_num, status in queues:
            status_icon = "✅" if status == 'active' else "❌"
            text += f"{status_icon} {dept_name}\n"
            text += f"👤 {client_name} | 📞 {phone}\n"
            text += f"🕐 {queue_time} | 🔢 {queue_num}\n"
            text += "─" * 30 + "\n"

    keyboard = [[InlineKeyboardButton("🔙 Orqaga", callback_data="admin_panel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text, reply_markup=reply_markup)


# Bo'lim qo'shish
async def add_department(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "Yangi bo'lim nomini kiriting:"
    )
    context.user_data['waiting_for'] = 'new_department'


# Admin qo'shish
async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "Yangi adminning Telegram user ID sini kiriting:\n\n"
        "User ID ni olish uchun @userinfobot dan foydalanishingiz mumkin."
    )
    context.user_data['waiting_for'] = 'new_admin'


# Callback query handler
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    if data == "get_queue":
        await show_departments(update, context)
    elif data == "my_queues":
        await show_my_queues(update, context)
    elif data == "admin_panel":
        # callback bo'lgani uchun query mavjud
        context.user_data['admin_login'] = True
        await query.answer()
        await query.message.reply_text("🔐 Admin paneliga kirish uchun 4 xonali kodni kiriting:")
    elif data == "main_menu":
        await start(update, context)
    elif data.startswith("dept_"):
        await show_available_times(update, context)
    elif data.startswith("time_"):
        await get_client_info(update, context)
    elif data.startswith("cancel_"):
        await cancel_appointment(update, context)
    elif data == "view_today_queues":
        await view_today_queues(update, context)
    elif data == "add_department":
        await add_department(update, context)
    elif data == "add_admin":
        await add_admin(update, context)



def main():
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_client_info))

    print("Bot yangilangan versiya bilan ishga tushdi...")
    application.run_polling()


if __name__ == '__main__':
    main()