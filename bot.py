#!/usr/bin/env python3
"""
MissRose_bot Clone - Comprehensive Telegram Group Management Bot
Created with 60+ working commands for complete group administration
"""

import os
import re
import json
import logging
import time
import psycopg2
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union, Any
from functools import wraps
import uuid

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.error import TelegramError, BadRequest, Forbidden
from telegram.constants import ParseMode

# help_content.py फ़ाइल से हेल्प टेक्स्ट इम्पोर्ट करें
from help_content import help_texts, support_text

# लॉगिंग कॉन्फ़िगर करें
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# एनवायरनमेंट वेरिएबल्स से कॉन्फ़िगरेशन
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
WEBHOOK_URL = os.getenv("WEBHOOK_URL") # Render द्वारा प्रदान किया गया
PORT = int(os.getenv("PORT", "8443"))


class Database:
    """बॉट डेटा के लिए PostgreSQL डेटाबेस हैंडलर"""

    def __init__(self, db_url):
        self.db_url = db_url
        if not self.db_url:
            logger.error("DATABASE_URL एनवायरनमेंट वेरिएबल में नहीं मिला!")
            raise ValueError("DATABASE_URL एनवायरनमेंट वेरिएबल सेट नहीं है।")

    def get_connection(self):
        """PostgreSQL डेटाबेस से कनेक्शन स्थापित करता है।"""
        return psycopg2.connect(self.db_url)

    def init_db(self):
        """डेटाबेस तालिकाओं को प्रारंभ करता है"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                # Groups टेबल
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS groups (
                        chat_id BIGINT PRIMARY KEY,
                        welcome_message TEXT,
                        goodbye_message TEXT,
                        rules TEXT,
                        private_rules BOOLEAN DEFAULT FALSE,
                        clean_welcome BOOLEAN DEFAULT FALSE,
                        clean_service BOOLEAN DEFAULT FALSE,
                        silent_actions BOOLEAN DEFAULT FALSE,
                        log_channel BIGINT,
                        federation_id TEXT,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                ''')
                # Users टेबल
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        user_id BIGINT PRIMARY KEY,
                        username TEXT,
                        first_name TEXT,
                        last_name TEXT,
                        is_banned BOOLEAN DEFAULT FALSE,
                        ban_reason TEXT,
                        ban_expires TIMESTAMP WITH TIME ZONE,
                        warnings INTEGER DEFAULT 0,
                        last_seen TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                ''')
                # Group restrictions टेबल
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS group_restrictions (
                        chat_id BIGINT,
                        user_id BIGINT,
                        restriction_type TEXT,
                        expires_at TIMESTAMP WITH TIME ZONE,
                        reason TEXT,
                        admin_id BIGINT,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        PRIMARY KEY (chat_id, user_id, restriction_type)
                    )
                ''')
                # Filters टेबल
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS filters (
                        chat_id BIGINT,
                        trigger_word TEXT,
                        response TEXT,
                        is_private BOOLEAN DEFAULT FALSE,
                        created_by BIGINT,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        PRIMARY KEY (chat_id, trigger_word)
                    )
                ''')
                # Locks टेबल
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS locks (
                        chat_id BIGINT,
                        lock_type TEXT,
                        is_locked BOOLEAN DEFAULT TRUE,
                        PRIMARY KEY (chat_id, lock_type)
                    )
                ''')
                # Disabled commands टेबल
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS disabled_commands (
                        chat_id BIGINT,
                        command TEXT,
                        PRIMARY KEY (chat_id, command)
                    )
                ''')
                # Federation टेबल
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS federations (
                        fed_id TEXT PRIMARY KEY,
                        fed_name TEXT,
                        owner_id BIGINT,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                ''')
                # Federation bans टेबल
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS fed_bans (
                        fed_id TEXT,
                        user_id BIGINT,
                        reason TEXT,
                        banned_by BIGINT,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        PRIMARY KEY (fed_id, user_id)
                    )
                ''')
                # Warnings टेबल
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS warnings (
                        id SERIAL PRIMARY KEY,
                        chat_id BIGINT,
                        user_id BIGINT,
                        reason TEXT,
                        warned_by BIGINT,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                ''')
            conn.commit()
            logger.info("डेटाबेस तालिकाएँ सफलतापूर्वक प्रारंभ हो गईं।")
        except Exception as e:
            logger.error(f"डेटाबेस प्रारंभ करने में त्रुटि: {e}")
            conn.rollback()
        finally:
            conn.close()

    def execute_query(self, query: str, params: tuple = (), fetch=None):
        """एक क्वेरी निष्पादित करता है और फ़ेच पैरामीटर के आधार पर परिणाम लौटाता है।"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                if fetch == 'one':
                    result = cursor.fetchone()
                elif fetch == 'all':
                    result = cursor.fetchall()
                else:
                    result = None
                conn.commit()
                return result
        except Exception as e:
            logger.error(f"क्वेरी '{query}' पर डेटाबेस त्रुटि: {e}")
            conn.rollback()
            return None
        finally:
            conn.close()

    def get_group_setting(self, chat_id: int, setting: str):
        """एक विशिष्ट समूह सेटिंग प्राप्त करें"""
        result = self.execute_query(
            f"SELECT {setting} FROM groups WHERE chat_id = %s", (chat_id,), fetch='one'
        )
        return result[0] if result else None

    def set_group_setting(self, chat_id: int, setting: str, value):
        """एक विशिष्ट समूह सेटिंग सेट करें"""
        query = f"""
            INSERT INTO groups (chat_id, {setting}) VALUES (%s, %s)
            ON CONFLICT (chat_id) DO UPDATE SET {setting} = EXCLUDED.{setting};
        """
        self.execute_query(query, (chat_id, value))

# डेटाबेस प्रारंभ करें
db = Database(DATABASE_URL)

# --- डेकोरेटर और यूटिलिटी फ़ंक्शंस ---

def admin_required(func):
    """यह जांचने के लिए डेकोरेटर कि उपयोगकर्ता एडमिन है या नहीं"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == 'private':
            return await func(update, context)
        
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        
        try:
            member = await context.bot.get_chat_member(chat_id, user_id)
            if member.status in ['administrator', 'creator']:
                return await func(update, context)
            else:
                if not db.get_group_setting(chat_id, 'silent_actions'):
                    await update.message.reply_text("❌ इस कमांड का उपयोग करने के लिए आपको एक एडमिन होना चाहिए।")
        except Exception as e:
            logger.error(f"एडमिन स्थिति की जाँच करते समय त्रुटि: {e}")
        
        return None
    return wrapper

def owner_required(func):
    """यह जांचने के लिए डेकोरेटर कि उपयोगकर्ता समूह का मालिक है या नहीं"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == 'private':
            return await func(update, context)
        
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        
        try:
            member = await context.bot.get_chat_member(chat_id, user_id)
            if member.status == 'creator':
                return await func(update, context)
            else:
                await update.message.reply_text("❌ केवल समूह का मालिक ही इस कमांड का उपयोग कर सकता है।")
        except Exception as e:
            logger.error(f"मालिक की स्थिति की जाँच करते समय त्रुटि: {e}")
        
        return None
    return wrapper

def parse_time(time_str: str) -> Optional[datetime]:
    """समय स्ट्रिंग जैसे '4m', '3h', '6d', '5w' को डेटटाइम में पार्स करें"""
    if not time_str:
        return None
    
    match = re.match(r'^(\d+)([mhdw])$', time_str.lower())
    if not match: return None
    
    amount, unit = int(match.group(1)), match.group(2)
    
    if unit == 'm': return datetime.now() + timedelta(minutes=amount)
    if unit == 'h': return datetime.now() + timedelta(hours=amount)
    if unit == 'd': return datetime.now() + timedelta(days=amount)
    if unit == 'w': return datetime.now() + timedelta(weeks=amount)
    return None

def get_user_from_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """संदेश से उपयोगकर्ता निकालें (उत्तर, उल्लेख, या आईडी)"""
    message = update.effective_message
    
    if message and message.reply_to_message:
        return message.reply_to_message.from_user
    
    if context.args and len(context.args) > 0:
        user_input = context.args[0]
        if user_input.startswith('@'): user_input = user_input[1:]
        
        try:
            return {"id": int(user_input), "username": None, "first_name": "Unknown"}
        except ValueError:
            return {"id": None, "username": user_input, "first_name": user_input}
    
    return None

def get_user_id(user_obj):
    """उपयोगकर्ता ऑब्जेक्ट से उपयोगकर्ता आईडी प्राप्त करें"""
    if user_obj is None: return None
    return getattr(user_obj, 'id', user_obj.get('id') if isinstance(user_obj, dict) else None)

def get_user_name(user_obj):
    """उपयोगकर्ता का प्रदर्शन नाम प्राप्त करें"""
    if user_obj is None: return "Unknown"
    return getattr(user_obj, 'first_name', user_obj.get('first_name') if isinstance(user_obj, dict) else "Unknown") or "Unknown"

async def log_action(context: ContextTypes.DEFAULT_TYPE, chat_id: int, action: str, details: str):
    """एडमिन क्रियाओं को लॉग चैनल में लॉग करें"""
    log_channel = db.get_group_setting(chat_id, 'log_channel')
    if not log_channel: return
    
    log_message = (f"🔍 **एडमिन एक्शन लॉग**\n\n"
                   f"**एक्शन:** {action}\n"
                   f"**विवरण:** {details}\n"
                   f"**समय:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                   f"**चैट:** {chat_id}")
    
    try:
        await context.bot.send_message(chat_id=log_channel, text=log_message, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"लॉग संदेश भेजने में विफल: {e}")

user_last_command = {}
def rate_limit(func):
    """रेट लिमिटिंग डेकोरेटर"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        current_time = time.time()
        if user_id in user_last_command and (current_time - user_last_command[user_id]) < 1:
            return
        user_last_command[user_id] = current_time
        return await func(update, context)
    return wrapper

# --- कमांड हैंडलर्स ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """स्टार्ट कमांड हैंडलर"""
    user = update.effective_user
    if update.effective_chat.type == 'private':
        welcome_text = f"👋 **नमस्ते {user.first_name}!**\n\nमैं **मिस रोज़** हूँ, आपका मैत्रीपूर्ण समूह प्रबंधन बॉट! 🌹\n\n**मैं क्या कर सकती हूँ:**\n• 🛡️ आपके समूह को स्पैम और अवांछित सामग्री से बचाना\n• 👥 उपयोगकर्ताओं का प्रबंधन (प्रतिबंध, म्यूट, किक, चेतावनी)\n• 📝 स्वागत संदेश और नियम सेट करना\n• 🤖 ऑटो-मॉडरेशन और फिल्टर\n\n**शुरू करना:**\n1. मुझे अपने समूह में एक एडमिन के रूप में जोड़ें\n2. सभी उपलब्ध कमांड देखने के लिए `/help` का उपयोग करें\n3. अपने समूह की सेटिंग्स कॉन्फ़िगर करें"
        keyboard = [
            [InlineKeyboardButton("📚 सहायता और कमांड", callback_data="help_main")],
            [InlineKeyboardButton("➕ समूह में जोड़ें", url=f"https://t.me/{context.bot.username}?startgroup=true")],
            [InlineKeyboardButton("💬 समर्थन", callback_data="support")]
        ]
        await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(f"👋 नमस्ते! मैं मिस रोज़ हूँ, इस समूह का प्रबंधन करने में मदद करने के लिए तैयार हूँ!")

@rate_limit
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """वर्गीकृत कमांड के साथ हेल्प कमांड"""
    keyboard = [
        [InlineKeyboardButton("👥 उपयोगकर्ता प्रबंधन", callback_data="help_users"), InlineKeyboardButton("🛡️ एडमिन उपकरण", callback_data="help_admin")],
        [InlineKeyboardButton("📝 स्वागत और नियम", callback_data="help_welcome"), InlineKeyboardButton("🔒 ताले और फिल्टर", callback_data="help_locks")],
        [InlineKeyboardButton("📊 लॉगिंग", callback_data="help_logging"), InlineKeyboardButton("🌐 फेडरेशन", callback_data="help_federation")],
        [InlineKeyboardButton("⚙️ सेटिंग्स", callback_data="help_settings"), InlineKeyboardButton("🔧 उपयोगिताएँ", callback_data="help_utils")]
    ]
    await update.message.reply_text(help_texts["main"], parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))

# --- उपयोगकर्ता प्रबंधन कमांड ---
@admin_required
@rate_limit
async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id, admin_user = update.effective_chat.id, update.effective_user
    target_user = get_user_from_message(update, context)
    if not target_user: return await update.message.reply_text("❌ कृपया किसी उपयोगकर्ता को उत्तर दें या उपयोगकर्ता नाम/आईडी प्रदान करें।")
    
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else "कोई कारण नहीं दिया गया"
    user_id = get_user_id(target_user)
    if not user_id: return await update.message.reply_text("❌ प्रतिबंधित करने के लिए उपयोगकर्ता की पहचान नहीं हो सकी।")

    try:
        await context.bot.ban_chat_member(chat_id, user_id)
        db.execute_query(
            "INSERT INTO group_restrictions (chat_id, user_id, restriction_type, reason, admin_id) VALUES (%s, %s, 'ban', %s, %s) ON CONFLICT (chat_id, user_id, restriction_type) DO UPDATE SET reason = EXCLUDED.reason",
            (chat_id, user_id, reason, admin_user.id)
        )
        if not db.get_group_setting(chat_id, 'silent_actions'):
            await update.message.reply_text(f"🔨 **उपयोगकर्ता प्रतिबंधित**\n\n**उपयोगकर्ता:** {get_user_name(target_user)}\n**कारण:** {reason}\n**एडमिन:** {admin_user.first_name}", parse_mode=ParseMode.MARKDOWN)
        await log_action(context, chat_id, "उपयोगकर्ता प्रतिबंध", f"उपयोगकर्ता {user_id} को {admin_user.id} द्वारा प्रतिबंधित किया गया: {reason}")
    except Exception as e: await update.message.reply_text(f"❌ उपयोगकर्ता को प्रतिबंधित करने में विफल: {e}")

@admin_required
@rate_limit
async def tban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id, admin_user = update.effective_chat.id, update.effective_user
    if len(context.args) < 1: return await update.message.reply_text("❌ उपयोग: `/tban <user> <time> [reason]`")

    target_user = get_user_from_message(update, context)
    if not target_user: return await update.message.reply_text("❌ कृपया किसी उपयोगकर्ता को उत्तर दें या उपयोगकर्ता नाम/आईडी प्रदान करें।")

    time_str = context.args[1] if update.message.reply_to_message and len(context.args) > 1 else context.args[0]
    ban_until = parse_time(time_str)
    if not ban_until: return await update.message.reply_text("❌ अमान्य समय प्रारूप। उपयोग करें: 4m, 3h, 6d, 5w")

    reason_start_index = 2 if update.message.reply_to_message and len(context.args) > 1 else 1
    reason = " ".join(context.args[reason_start_index:]) or "कोई कारण नहीं दिया गया"
    user_id = get_user_id(target_user)
    if not user_id: return await update.message.reply_text("❌ प्रतिबंधित करने के लिए उपयोगकर्ता की पहचान नहीं हो सकी।")

    try:
        await context.bot.ban_chat_member(chat_id, user_id, until_date=ban_until)
        db.execute_query(
            "INSERT INTO group_restrictions (chat_id, user_id, restriction_type, expires_at, reason, admin_id) VALUES (%s, %s, 'tban', %s, %s, %s) ON CONFLICT (chat_id, user_id, restriction_type) DO UPDATE SET expires_at = EXCLUDED.expires_at, reason = EXCLUDED.reason",
            (chat_id, user_id, ban_until, reason, admin_user.id)
        )
        if not db.get_group_setting(chat_id, 'silent_actions'):
            await update.message.reply_text(f"⏰ **उपयोगकर्ता अस्थायी रूप से प्रतिबंधित**\n\n**उपयोगकर्ता:** {get_user_name(target_user)}\n**अवधि:** {time_str}\n**कारण:** {reason}", parse_mode=ParseMode.MARKDOWN)
        await log_action(context, chat_id, "अस्थायी प्रतिबंध", f"उपयोगकर्ता {user_id} को {admin_user.id} द्वारा {time_str} के लिए प्रतिबंधित किया गया: {reason}")
    except Exception as e: await update.message.reply_text(f"❌ अस्थायी रूप से प्रतिबंधित करने में विफल: {e}")

@admin_required
@rate_limit
async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id, admin_user = update.effective_chat.id, update.effective_user
    target_user = get_user_from_message(update, context)
    if not target_user: return await update.message.reply_text("❌ कृपया किसी उपयोगकर्ता को उत्तर दें या उपयोगकर्ता नाम/आईडी प्रदान करें।")
    
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else "कोई कारण नहीं दिया गया"
    user_id = get_user_id(target_user)
    if not user_id: return await update.message.reply_text("❌ म्यूट करने के लिए उपयोगकर्ता की पहचान नहीं हो सकी।")

    permissions = ChatPermissions(can_send_messages=False)
    try:
        await context.bot.restrict_chat_member(chat_id, user_id, permissions)
        db.execute_query(
            "INSERT INTO group_restrictions (chat_id, user_id, restriction_type, reason, admin_id) VALUES (%s, %s, 'mute', %s, %s) ON CONFLICT (chat_id, user_id, restriction_type) DO UPDATE SET reason = EXCLUDED.reason",
            (chat_id, user_id, reason, admin_user.id)
        )
        if not db.get_group_setting(chat_id, 'silent_actions'):
            await update.message.reply_text(f"🔇 **उपयोगकर्ता म्यूट**\n\n**उपयोगकर्ता:** {get_user_name(target_user)}\n**कारण:** {reason}", parse_mode=ParseMode.MARKDOWN)
        await log_action(context, chat_id, "उपयोगकर्ता म्य
