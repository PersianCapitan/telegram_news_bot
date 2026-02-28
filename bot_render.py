"""
🤖 ربات خبری تلگرام - نسخه Render.com
نسخه بهینه شده برای Deploy در Render

استفاده از Bot Token از @BotFather
دیباگ کامل، خطاهای واضح، لاگ حرفه‌ای
"""

import asyncio
import json
import hashlib
import logging
import sys
import os
from telethon import TelegramClient, events, Button
from telethon.errors import (
    FloodWaitError, 
    ChatWriteForbiddenError,
    ChannelPrivateError,
    UserNotParticipantError,
    AuthKeyError,
    ServerError
)
from datetime import datetime, timedelta

# ═══════════════════════════════════════════════════════════════════
# تنظیمات لاگ
# ═══════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# تنظیمات - از Environment Variables میخونه (برای Render)
# ═══════════════════════════════════════════════════════════════════

# اولویت: Environment Variables (برای Render)
# بعد: مقادیر پیش‌فرض (برای تست محلی)

API_ID = os.getenv('API_ID', 'YOUR_API_ID')
API_HASH = os.getenv('API_HASH', 'YOUR_API_HASH')
BOT_TOKEN = os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN')

# تنظیمات کانال‌ها - می‌تونی مستقیم اینجا بنویسی
# یا از env variable استفاده کنی
CHANNEL_CONFIG = {
    '@bbc_persian': {
        'dest': '@my_news_channel',
        'footer': '\n\n📰 منبع: BBC فارسی'
    },
    # کانال‌های بیشتر اضافه کن...
}

# متن‌های تبلیغاتی
AD_TEXTS = [
    'عضویت در کانال',
    '@promo',
    'کلیک کنید',
    'لینک دانلود',
    '🔻 عضویت',
    '👇 کانال ما',
    '══════════',
    '──────────',
]

# تنظیمات
SEND_MODE = 'copy'
ADD_SOURCE_BUTTON = True
DELAY_BETWEEN_POSTS = 2
MAX_MESSAGE_LENGTH = 4000
SEND_OLD_MESSAGES = False
OLD_MESSAGES_LIMIT = 5
SENT_MESSAGES_FILE = 'sent_messages.json'

# ═══════════════════════════════════════════════════════════════════
# کلاس ربات
# ═══════════════════════════════════════════════════════════════════

class TelegramNewsBot:
    def __init__(self):
        logger.info("="*50)
        logger.info("🤖 ربات خبری در حال راه‌اندازی...")
        logger.info("="*50)
        
        self._check_config()
        
        self.client = TelegramClient(
            'bot_session',
            int(API_ID),
            API_HASH,
            connection_retries=5,
            retry_delay=3,
            timeout=30
        )
        
        self.sent_messages = self._load_sent_messages()
        self.stats = {
            'total_sent': 0,
            'duplicates': 0,
            'errors': 0,
            'start_time': datetime.now()
        }
        
        logger.info(f"📊 تاریخچه: {len(self.sent_messages)} پیام")
    
    def _check_config(self):
        """بررسی تنظیمات"""
        errors = []
        
        if API_ID == 'YOUR_API_ID':
            errors.append("❌ API_ID تنظیم نشده!")
        
        if API_HASH == 'YOUR_API_HASH':
            errors.append("❌ API_HASH تنظیم نشده!")
        
        if BOT_TOKEN == 'YOUR_BOT_TOKEN':
            errors.append("❌ BOT_TOKEN تنظیم نشده!")
        
        if not CHANNEL_CONFIG:
            errors.append("❌ کانالی تنظیم نشده!")
        
        if errors:
            logger.error("\n🚨 خطاهای تنظیمات:")
            for error in errors:
                logger.error(error)
            logger.error("\n💡 راه‌حل:")
            logger.error("در Render: Dashboard → Environment → Add Variable")
            logger.error("API_ID = 12345678")
            logger.error("API_HASH = abcd...")
            logger.error("BOT_TOKEN = 1234:ABC...")
            sys.exit(1)
        
        logger.info("✅ تنظیمات OK")
    
    def _load_sent_messages(self):
        """بارگذاری تاریخچه"""
        try:
            with open(SENT_MESSAGES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning("⚠️ فایل تاریخچه جدید")
            return {}
        except Exception as e:
            logger.error(f"❌ خطا در بارگذاری: {e}")
            return {}
    
    def _save_sent_messages(self):
        """ذخیره تاریخچه"""
        try:
            # پاکسازی قدیمی‌ها (بالای 7 روز)
            week_ago = (datetime.now() - timedelta(days=7)).isoformat()
            self.sent_messages = {
                k: v for k, v in self.sent_messages.items()
                if v > week_ago
            }
            
            with open(SENT_MESSAGES_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.sent_messages, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"❌ خطا در ذخیره: {e}")
    
    def _get_message_hash(self, text):
        """Hash برای تشخیص تکراری"""
        if not text:
            return None
        try:
            cleaned = ' '.join(text.split()).lower()
            return hashlib.md5(cleaned.encode()).hexdigest()
        except:
            return None
    
    def _is_duplicate(self, text, hours=24):
        """چک تکراری"""
        if not text:
            return False
        
        msg_hash = self._get_message_hash(text)
        if not msg_hash:
            return False
        
        try:
            if msg_hash in self.sent_messages:
                sent_time = datetime.fromisoformat(self.sent_messages[msg_hash])
                if datetime.now() - sent_time < timedelta(hours=hours):
                    self.stats['duplicates'] += 1
                    return True
            
            self.sent_messages[msg_hash] = datetime.now().isoformat()
            self._save_sent_messages()
            return False
        except:
            return False
    
    def _remove_ads(self, text):
        """حذف تبلیغات"""
        if not text:
            return text
        
        try:
            lines = text.split('\n')
            cleaned_lines = []
            
            for line in lines:
                keep = True
                for ad in AD_TEXTS:
                    if ad.lower() in line.lower():
                        keep = False
                        break
                if keep:
                    cleaned_lines.append(line)
            
            result = '\n'.join(cleaned_lines)
            while '\n\n\n' in result:
                result = result.replace('\n\n\n', '\n\n')
            
            return result.strip()
        except:
            return text
    
    def _create_button(self, source):
        """ساخت دکمه منبع"""
        if not ADD_SOURCE_BUTTON or not source:
            return None
        try:
            username = source.lstrip('@')
            if username.startswith('-'):
                return None
            return [[Button.url("📡 منبع", f"https://t.me/{username}")]]
        except:
            return None
    
    async def _send_message(self, event, dest, footer='', source=''):
        """ارسال پیام"""
        try:
            text = event.message.message or ''
            text = self._remove_ads(text)
            
            # طول متن
            if text and len(text) > MAX_MESSAGE_LENGTH - len(footer):
                text = text[:MAX_MESSAGE_LENGTH - len(footer) - 20] + "\n...[ادامه]"
            
            # Footer
            final = (text + footer) if text and footer else (text or footer.strip())
            
            # تکراری
            if self._is_duplicate(text or "media"):
                logger.info("🔄 تکراری")
                return False
            
            # دکمه
            btn = self._create_button(source) if SEND_MODE == 'copy' else None
            
            # تاخیر
            await asyncio.sleep(DELAY_BETWEEN_POSTS)
            
            # ارسال
            if SEND_MODE == 'forward':
                await self.client.forward_messages(dest, event.message)
            else:
                if event.message.media:
                    await self.client.send_message(
                        dest,
                        final if final else None,
                        file=event.message.media,
                        buttons=btn
                    )
                elif final:
                    await self.client.send_message(dest, final, buttons=btn)
                else:
                    return False
            
            self.stats['total_sent'] += 1
            logger.info(f"✅ ارسال شد → {dest} | #{self.stats['total_sent']}")
            return True
        
        except FloodWaitError as e:
            logger.warning(f"⏳ FloodWait: {e.seconds}s")
            await asyncio.sleep(e.seconds)
            return await self._send_message(event, dest, footer, source)
        
        except ChatWriteForbiddenError:
            logger.error(f"❌ دسترسی نداریم به {dest}")
            logger.error("💡 ربات باید ادمین باشه")
            self.stats['errors'] += 1
            return False
        
        except ChannelPrivateError:
            logger.error(f"❌ {dest} خصوصی یا عضو نیستیم")
            self.stats['errors'] += 1
            return False
        
        except Exception as e:
            logger.error(f"❌ خطا: {type(e).__name__}: {str(e)}")
            self.stats['errors'] += 1
            return False
    
    async def _send_album(self, event, dest, footer='', source=''):
        """ارسال آلبوم"""
        try:
            messages = await self.client.get_messages(
                event.chat_id,
                ids=[event.message.id + i for i in range(-10, 10)]
            )
            
            grouped = [
                m for m in messages
                if m and hasattr(m, 'grouped_id') and m.grouped_id == event.message.grouped_id
            ]
            
            if not grouped:
                return await self._send_message(event, dest, footer, source)
            
            grouped.sort(key=lambda x: x.id)
            
            text = ''
            for m in grouped:
                if m.message:
                    text = m.message
                    break
            
            text = self._remove_ads(text)
            final = (text + footer) if text and footer else (text or footer.strip())
            
            if self._is_duplicate(text or f"album_{event.message.grouped_id}"):
                logger.info("🔄 آلبوم تکراری")
                return False
            
            btn = self._create_button(source) if SEND_MODE == 'copy' else None
            await asyncio.sleep(DELAY_BETWEEN_POSTS)
            
            if SEND_MODE == 'forward':
                await self.client.forward_messages(dest, grouped)
            else:
                files = [m.media for m in grouped if m.media]
                if files:
                    await self.client.send_message(
                        dest,
                        final if final else None,
                        file=files,
                        buttons=btn
                    )
            
            self.stats['total_sent'] += 1
            logger.info(f"✅ آلبوم ({len(grouped)}) → {dest}")
            return True
        
        except Exception as e:
            logger.error(f"❌ خطا در آلبوم: {e}")
            return False
    
    async def _check_access(self):
        """بررسی دسترسی کانال‌ها"""
        logger.info("\n" + "="*50)
        logger.info("🔍 بررسی کانال‌ها...")
        logger.info("="*50)
        
        ok = True
        for source, cfg in CHANNEL_CONFIG.items():
            dest = cfg['dest'] if isinstance(cfg, dict) else cfg
            
            # منبع
            try:
                ent = await self.client.get_entity(source)
                logger.info(f"✅ {source}")
            except Exception as e:
                logger.error(f"❌ {source}: {e}")
                ok = False
            
            # مقصد
            try:
                ent = await self.client.get_entity(dest)
                perm = await self.client.get_permissions(dest, 'me')
                
                if perm.is_admin and perm.post_messages:
                    logger.info(f"✅ {dest} - ادمین")
                else:
                    logger.error(f"❌ {dest} - ادمین نیست!")
                    ok = False
            except Exception as e:
                logger.error(f"❌ {dest}: {e}")
                ok = False
        
        logger.info("="*50)
        if not ok:
            logger.warning("⚠️ برخی کانال‌ها مشکل دارند")
        else:
            logger.info("✅ همه کانال‌ها آماده")
        logger.info("="*50 + "\n")
    
    async def start(self):
        """شروع ربات"""
        retry_count = 0
        max_retries = 5
        
        while retry_count < max_retries:
            try:
                logger.info(f"🔌 اتصال... (تلاش {retry_count + 1}/{max_retries})")
                
                await self.client.start(bot_token=BOT_TOKEN)
                
                me = await self.client.get_me()
                logger.info(f"✅ ربات: @{me.username}")
                logger.info(f"🆔 ID: {me.id}")
                logger.info(f"📤 حالت: {SEND_MODE}")
                logger.info(f"⏱️  تاخیر: {DELAY_BETWEEN_POSTS}s")
                
                await self._check_access()
                
                # Handler
                processed = set()
                
                for source, cfg in CHANNEL_CONFIG.items():
                    dest = cfg['dest'] if isinstance(cfg, dict) else cfg
                    footer = cfg.get('footer', '') if isinstance(cfg, dict) else ''
                    
                    @self.client.on(events.NewMessage(chats=source))
                    async def handler(event, d=dest, f=footer, s=source):
                        try:
                            logger.info(f"\n📨 از {s}")
                            
                            if hasattr(event.message, 'grouped_id') and event.message.grouped_id:
                                if event.message.grouped_id not in processed:
                                    processed.add(event.message.grouped_id)
                                    await self._send_album(event, d, f, s)
                                    
                                    async def clean(gid):
                                        await asyncio.sleep(60)
                                        processed.discard(gid)
                                    
                                    asyncio.create_task(clean(event.message.grouped_id))
                            else:
                                await self._send_message(event, d, f, s)
                        
                        except Exception as e:
                            logger.error(f"❌ Handler: {e}")
                
                logger.info("\n" + "🟢"*25)
                logger.info("🤖 ربات فعال!")
                logger.info("📡 در حال نظارت...")
                logger.info("🟢"*25 + "\n")
                
                # آمار هر 1 ساعت
                async def stats():
                    while True:
                        await asyncio.sleep(3600)
                        runtime = datetime.now() - self.stats['start_time']
                        logger.info(f"\n📊 آمار:")
                        logger.info(f"✅ ارسال: {self.stats['total_sent']}")
                        logger.info(f"🔄 تکراری: {self.stats['duplicates']}")
                        logger.info(f"❌ خطا: {self.stats['errors']}")
                        logger.info(f"⏱️  زمان: {runtime.seconds//3600}h\n")
                
                asyncio.create_task(stats())
                
                await self.client.run_until_disconnected()
                break
            
            except AuthKeyError:
                logger.error("❌ خطای احراز هویت - حذف session")
                try:
                    os.remove('bot_session.session')
                except:
                    pass
                retry_count += 1
                await asyncio.sleep(5)
            
            except ServerError:
                logger.error("❌ خطای سرور - تلاش مجدد...")
                retry_count += 1
                await asyncio.sleep(10)
            
            except Exception as e:
                logger.error(f"❌ خطا: {type(e).__name__}: {str(e)}")
                retry_count += 1
                await asyncio.sleep(5)
        
        if retry_count >= max_retries:
            logger.critical("💥 اتصال ناموفق بعد از 5 تلاش!")
            sys.exit(1)

# ═══════════════════════════════════════════════════════════════════
# اجرای اصلی
# ═══════════════════════════════════════════════════════════════════

def main():
    try:
        bot = TelegramNewsBot()
        asyncio.run(bot.start())
    except KeyboardInterrupt:
        logger.info("\n👋 خداحافظ!")
    except Exception as e:
        logger.critical(f"\n💥 خطای کلی: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
