import sqlite3
import asyncio
import aiohttp
import re
import time
import phonenumbers
import io
import pandas as pd
import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler
from telegram.error import NetworkError

# Configuration
TOKEN = os.environ.get('TOKEN', '8816168770:AAEQpphmhhPXEBPwQTcBT2Gl4kfw8IpX_F4')
ADMIN_USERNAME = 'foysal92700'
API_TOKEN = os.environ.get('API_TOKEN', 'RldRSkpBUzRRhgodqV4OGSEGUjl9ikGFDWI-LSYWJdGJFbFNGYI5kiA==')
API_URL = "http://147.135.212.197/crapi/st/viewstats" 

TELEGRAM_CHAT_ID = '-1003942289262'
CHANNEL_ID = '@ghfujtyjtt'       
GROUP_ID = '@hehejejwvwjehdud'    

CHANNEL_URL = "https://t.me/ghfujtyjtt"
GROUP_URL = "https://t.me/hehejejwvwjehdud"

# Database Setup
DB_PATH = '/tmp/numbers.db'
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS numbers 
                  (id INTEGER PRIMARY KEY, service TEXT, country TEXT, number TEXT, status TEXT, user_id INTEGER, expiry_time REAL, message_id INTEGER)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS expired_numbers 
                  (id INTEGER PRIMARY KEY, number TEXT UNIQUE, country TEXT)''')

try:
    cursor.execute('ALTER TABLE expired_numbers ADD COLUMN country TEXT')
    conn.commit()
except sqlite3.OperationalError: pass

try:
    cursor.execute('ALTER TABLE numbers ADD COLUMN message_id INTEGER')
    conn.commit()
except sqlite3.OperationalError: pass

SERVICE, COUNTRY, NUMBERS = range(3)
active_checking_numbers = {}

def get_country_details(phone_number):
    try:
        clean_num = re.sub(r'\D', '', phone_number)
        parsed = phonenumbers.parse('+' + clean_num, None)
        code = phonenumbers.region_code_for_number(parsed)
        if code:
            flag = "".join(chr(127397 + ord(c)) for c in code.upper())
            return flag, code.upper()
    except: pass
    return "🌍", "UN"

def get_flag_by_country_name(country_name):
    try:
        c_name = country_name.strip().title()
        custom_mapping = {
            "Venezuela": "VE", "Bangladesh": "BD", "India": "IN", "Russia": "RU", 
            "United States": "US", "Uk": "GB", "United Kingdom": "GB", "Vietnam": "VN",
            "Cambodia": "KH", "Indonesia": "ID", "Malaysia": "MY", "Thailand": "TH",
            "Philippines": "PH", "Myanmar": "MM", "Laos": "LA", "Singapore": "SG"
        }
        if c_name in custom_mapping:
            code = custom_mapping[c_name]
            return "".join(chr(127397 + ord(c)) for c in code.upper())
            
        for code, name in phonenumbers.locale.LocaleStringProvider()._get_all_regions().items():
            if name.lower() == c_name.lower():
                return "".join(chr(127397 + ord(c)) for c in code.upper())
    except: pass
    return "🚩"

async def is_user_joined(application, user_id):
    if str(user_id) == str(ADMIN_USERNAME): return True
    try:
        member_ch = await application.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        member_gr = await application.bot.get_chat_member(chat_id=GROUP_ID, user_id=user_id)
        valid_statuses = ['creator', 'administrator', 'member']
        if member_ch.status in valid_statuses and member_gr.status in valid_statuses: return True
    except: return False
    return False

async def send_force_join_msg(update, context, application, is_callback=False):
    keyboard = [
        [InlineKeyboardButton("📢 Join Channel", url=CHANNEL_URL)],
        [InlineKeyboardButton("💬 Join OTP Group", url=GROUP_URL)],
        [InlineKeyboardButton("✅ Verify", callback_data="verify_join")]
    ]
    text = "⚠️ **Access Denied!**\n\nআমাদের বটটি ব্যবহার করতে হলে তোকে প্রথমে আমাদের অফিশিয়াল চ্যানেল এবং ওটিপি গ্রুপে জয়েন করতে হবে।"
    if is_callback: await update.callback_query.answer("❌ তুই এখনো সবগুলোতে জয়েন করিসনি!", show_alert=True)
    else: await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def check_sms_loop(application):
    while True:
        try:
            current_time = time.time()
            expired_keys = []
            for num, details in list(active_checking_numbers.items()):
                if current_time > details['expiry_time']:
                    expired_keys.append(num)
                    try:
                        cursor.execute('INSERT OR IGNORE INTO expired_numbers (number, country) VALUES (?, ?)', (num, details['country']))
                        conn.commit()
                    except: pass
                    if details['message_id']:
                        try:
                            keyboard = [[InlineKeyboardButton("♻️ Change Number", callback_data=f"country_{details['service']}_{details['country']}")], [InlineKeyboardButton("🔙 Back to Menu", callback_data='menu_start')]]
                            await application.bot.edit_message_text(chat_id=details['user_id'], message_id=details['message_id'], text="❌ The number has expired.", reply_markup=InlineKeyboardMarkup(keyboard))
                        except: pass
            for key in expired_keys:
                if key in active_checking_numbers: del active_checking_numbers[key]

            if active_checking_numbers:
                headers = {'Authorization': f'Bearer {API_TOKEN}'}
                async with aiohttp.ClientSession() as session:
                    done_keys = []
                    for num, details in list(active_checking_numbers.items()):
                        try:
                            async with session.get(API_URL, headers=headers, params={'FilterNumber': num}, timeout=5) as response:
                                if response.status == 200:
                                    data = await response.json()
                                    if data and isinstance(data, list) and "message" in data[0]:
                                        msg = data[0]["message"]
                                        otp_match = re.search(r'(\d{3}-\d{3}|\d{6})', msg)
                                        if otp_match:
                                            otp = otp_match.group(0).replace('-', '')
                                            flag = get_flag_by_country_name(details['country'])
                                            success_msg = f"{flag} *{details['country']} {details['service']} Number*\n\n`+{num}`\n\n✅ **OTP Received!**"
                                            try: await application.bot.edit_message_text(chat_id=details['user_id'], message_id=details['message_id'], text=success_msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data='menu_start')]]), parse_mode='Markdown')
                                            except: pass
                                            await application.bot.send_message(chat_id=details['user_id'], text=f"✅ OTP: `{otp}`", parse_mode='Markdown')
                                            flag, country_code = get_country_details(num)
                                            try: await application.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f"{flag} *#{country_code} {details['service']} OTP Received*\n\n🔓 *OTP:* `{otp}`\n☎️ *Number:* `{num}`", parse_mode='Markdown')
                                            except: pass
                                            done_keys.append(num)
                        except: continue
                    for key in done_keys:
                        if key in active_checking_numbers: del active_checking_numbers[key]
        except: pass
        await asyncio.sleep(5)

async def show_main_menu(update, context, query=None):
    fixed = ["WhatsApp", "Telegram"]
    cursor.execute('SELECT DISTINCT service FROM numbers WHERE status="Available"')
    all_services = list(set(fixed + [row[0] for row in cursor.fetchall()]))
    keyboard = []
    for s in all_services:
        cursor.execute('SELECT COUNT(*) FROM numbers WHERE service=? AND status="Available"', (s,))
        count = cursor.fetchone()[0]
        if s in fixed or count > 0: keyboard.append([InlineKeyboardButton(f"{s} ({count})", callback_data=f'service_{s}')])
    if query: await query.edit_message_text("📱 Select a Service:", reply_markup=InlineKeyboardMarkup(keyboard))
    else: await update.message.reply_text("📱 Select a Service:", reply_markup=InlineKeyboardMarkup(keyboard))

async def start(update, context):
    user_id = update.effective_user.id
    context.user_data.clear()
    if update.effective_user.username != ADMIN_USERNAME and not await is_user_joined(context.application, user_id):
        await send_force_join_msg(update, context, context.application)
        return ConversationHandler.END
    if update.effective_user.username == ADMIN_USERNAME:
        keyboard = [[InlineKeyboardButton("📥 Input Numbers", callback_data='input_start')], [InlineKeyboardButton("🗑️ Delete Options", callback_data='del_menu')], [InlineKeyboardButton("📄 Export Expired Numbers", callback_data='export_expired')]]
        await update.message.reply_text("👋 Admin Mode!", reply_markup=InlineKeyboardMarkup(keyboard))
    else: await show_main_menu(update, context)
    return ConversationHandler.END

async def verify_callback(update, context):
    query = update.callback_query
    if await is_user_joined(context.application, update.effective_user.id):
        await query.answer("✅ ভেরিফিকেশন সফল!", show_alert=True)
        await show_main_menu(update, context, query=query)
    else: await send_force_join_msg(update, context, context.application, is_callback=True)

async def admin_delete_menu(update, context):
    query = update.callback_query
    cursor.execute('SELECT DISTINCT country FROM numbers')
    countries = cursor.fetchall()
    keyboard = [[InlineKeyboardButton(f"{get_flag_by_country_name(c[0])} {c[0]}", callback_data=f'del_country_{c[0]}')] for c in countries]
    keyboard.append([InlineKeyboardButton("🔙 Back to Admin", callback_data='admin_main')])
    await query.edit_message_text("Select country to delete:", reply_markup=InlineKeyboardMarkup(keyboard))

async def confirm_delete_country(update, context):
    query = update.callback_query
    country = query.data.replace('del_country_', '')
    cursor.execute('DELETE FROM numbers WHERE country=?', (country,))
    conn.commit()
    await query.edit_message_text(f"✅ All numbers for {country} deleted.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Admin", callback_data='admin_main')]]))

async def admin_main(update, context):
    query = update.callback_query
    context.user_data.clear()
    keyboard = [[InlineKeyboardButton("📥 Input Numbers", callback_data='input_start')], [InlineKeyboardButton("🗑️ Delete Options", callback_data='del_menu')], [InlineKeyboardButton("📄 Export Expired Numbers", callback_data='export_expired')]]
    await query.edit_message_text("👋 Admin Mode!", reply_markup=InlineKeyboardMarkup(keyboard))

async def export_expired_callback(update, context):
    query = update.callback_query
    await query.answer("Generating files... ⏳")
    cursor.execute('SELECT DISTINCT country FROM expired_numbers')
    countries = cursor.fetchall()
    if not countries:
        await query.answer("❌ কোনো ডাটা নেই!", show_alert=True)
        return
    for row in countries:
        cursor.execute('SELECT number FROM expired_numbers WHERE country=?', (row[0],))
        num_rows = cursor.fetchall()
        if num_rows:
            expired_list = [num[0] for num in num_rows]
            file_content = "\n".join(expired_list)
            file_bytes = io.BytesIO(file_content.encode('utf-8'))
            file_bytes.name = f"{row[0].lower().replace(' ', '_')}_expired.txt"
            await context.bot.send_document(chat_id=update.effective_user.id, document=file_bytes, caption=f"**{row[0]} Expired List**")
    cursor.execute('DELETE FROM expired_numbers')
    conn.commit()
    await context.bot.send_message(chat_id=update.effective_user.id, text="✅ ফাইল পাঠানো শেষ!")

async def service_callback(update, context):
    query = update.callback_query
    user_id = update.effective_user.id
    if update.effective_user.username != ADMIN_USERNAME and not await is_user_joined(context.application, user_id):
        await send_force_join_msg(update, context, context.application, is_callback=True)
        return
    service = query.data.split('_')[1]
    cursor.execute('SELECT country, COUNT(*) FROM numbers WHERE service=? AND status="Available" GROUP BY country', (service,))
    keyboard = []
    for row in cursor.fetchall():
        keyboard.append([InlineKeyboardButton(f"{get_flag_by_country_name(row[0])} {row[0]} ({row[1]})", callback_data=f"country_{service}_{row[0]}")])
    keyboard.append([InlineKeyboardButton("🔙 Back to Menu", callback_data='menu_start')])
    await query.edit_message_text(f"{service} - Select Country:", reply_markup=InlineKeyboardMarkup(keyboard))

async def country_callback(update, context):
    query = update.callback_query
    user_id = update.effective_user.id
    if update.effective_user.username != ADMIN_USERNAME and not await is_user_joined(context.application, user_id):
        await send_force_join_msg(update, context, context.application, is_callback=True)
        return
    data = query.data.split('_')
    service, country = data[1], data[2]
    cursor.execute('SELECT id, number FROM numbers WHERE service=? AND country=? AND status="Available" LIMIT 1', (service, country))
    row = cursor.fetchone()
    if row:
        num_id, num_str = row[0], row[1]
        expiry = time.time() + 180
        msg_text = f"*{country} {service} Number*\n\n`+{num_str}`\n\n🔄 Waiting for OTP..."
        cursor.execute('DELETE FROM numbers WHERE id=?', (num_id,))
        conn.commit()
        msg = await query.edit_message_text(text=msg_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='menu_start')]]), parse_mode='Markdown')
        active_checking_numbers[num_str] = {'user_id': user_id, 'expiry_time': expiry, 'message_id': msg.message_id, 'service': service, 'country': country}
    else: await query.answer("❌ No numbers available.", show_alert=True)

async def input_start(update, context):
    await update.callback_query.edit_message_text("Enter Service Name:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data='cancel_input')]]))
    return SERVICE

async def get_service(update, context):
    context.user_data['service'] = update.message.text
    await update.message.reply_text("Enter Country Name:")
    return COUNTRY

async def get_country(update, context):
    context.user_data['country'] = update.message.text
    await update.message.reply_text("📥 নাম্বারগুলো দে (পেস্ট বা ফাইল):")
    return NUMBERS

def extract_numbers_from_text(raw_text):
    found = re.findall(r'\+?\d{7,15}', raw_text)
    return list(set([re.sub(r'\D', '', num) for num in found if len(re.sub(r'\D', '', num)) >= 7]))

async def get_numbers(update, context):
    service, country = context.user_data['service'], context.user_data['country']
    extracted_numbers = []
    if update.message.document:
        doc = update.message.document
        file_obj = await context.bot.get_file(doc.file_id)
        file_bytes = await file_obj.download_as_bytearray()
        try:
            if doc.file_name.endswith('.xlsx'): extracted_numbers = extract_numbers_from_text(" ".join(pd.read_excel(io.BytesIO(file_bytes)).astype(str).values.flatten()))
            else: extracted_numbers = extract_numbers_from_text(file_bytes.decode('utf-8', errors='ignore'))
        except: await update.message.reply_text("❌ ফাইল রিড এরর!"); return ConversationHandler.END
    elif update.message.text: extracted_numbers = extract_numbers_from_text(update.message.text)
    if extracted_numbers:
        for num in extracted_numbers: cursor.execute('INSERT OR IGNORE INTO numbers (service, country, number, status) VALUES (?, ?, ?, ?)', (service, country, num, 'Available'))
        conn.commit()
        await update.message.reply_text(f"✅ সম্পন্ন! মোট: `{len(extracted_numbers)}`টি।")
    else: await update.message.reply_text("❌ কোনো নাম্বার পাওয়া যায়নি।")
    return ConversationHandler.END

async def cancel_input(update, context):
    context.user_data.clear()
    await update.callback_query.edit_message_text("❌ Cancelled.")
    return ConversationHandler.END

async def menu_start_callback(update, context):
    await show_main_menu(update, context, query=update.callback_query)

if __name__ == '__main__':
    application = ApplicationBuilder().token(TOKEN).build()
    
    # Render এর জন্য ফিক্সড ইভেন্ট লুপ
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    loop.create_task(check_sms_loop(application))
    
    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(input_start, pattern='input_start')],
        states={
            SERVICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_service), CallbackQueryHandler(cancel_input, pattern='cancel_input')],
            COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_country), CallbackQueryHandler(cancel_input, pattern='cancel_input')],
            NUMBERS: [MessageHandler((filters.TEXT | filters.Document.ALL) & ~filters.COMMAND, get_numbers), CallbackQueryHandler(cancel_input, pattern='cancel_input')]
        }, 
        fallbacks=[CommandHandler("start", start), CallbackQueryHandler(cancel_input, pattern='cancel_input')]
    )
    
    application.add_handler(conv)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(verify_callback, pattern='verify_join'))
    application.add_handler(CallbackQueryHandler(service_callback, pattern='service_'))
    application.add_handler(CallbackQueryHandler(country_callback, pattern='country_'))
    application.add_handler(CallbackQueryHandler(admin_main, pattern='admin_main'))
    application.add_handler(CallbackQueryHandler(admin_delete_menu, pattern='del_menu'))
    application.add_handler(CallbackQueryHandler(confirm_delete_country, pattern='del_country_'))
    application.add_handler(CallbackQueryHandler(menu_start_callback, pattern='menu_start'))
    application.add_handler(CallbackQueryHandler(export_expired_callback, pattern='export_expired'))
    
    try:
        application.run_polling()
    except Exception as e:
        print(f"Error: {e}")
