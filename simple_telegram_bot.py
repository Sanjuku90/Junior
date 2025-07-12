
import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
TELEGRAM_BOT_TOKEN = "7703189686:AAGArcOUnZImdOUTkwBggcyI9QSk5GSAB10"
DATABASE = 'investment_platform.db'

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def get_user_by_telegram_id(telegram_id):
    try:
        conn = get_db_connection()
        # Check if telegram_id column exists, if not create it
        cursor = conn.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'telegram_id' not in columns:
            conn.execute('ALTER TABLE users ADD COLUMN telegram_id INTEGER')
            conn.commit()
        
        user = conn.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
        conn.close()
        return user
    except Exception as e:
        print(f"Erreur get_user_by_telegram_id: {e}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /start"""
    telegram_user = update.effective_user
    user = get_user_by_telegram_id(telegram_user.id)
    
    if user:
        message = f"""
🏛️ **INVESTCRYPTO PRO**

👋 Salut {user['first_name']} !

💰 **Solde :** {user['balance']:.2f} USDT

🚀 Bot Telegram fonctionnel !
        """
    else:
        message = """
🏛️ **INVESTCRYPTO PRO**

👋 Bienvenue sur notre plateforme d'investissement !

Pour accéder à vos données, veuillez d'abord vous inscrire sur notre site web.

🌐 **Site web :** https://votre-repl-url.replit.dev
        """
    
    await update.message.reply_text(message, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /help"""
    message = """
❓ **AIDE**

**Commandes disponibles :**
/start - Menu principal
/help - Cette aide

🌐 **Pour investir :** Utilisez notre site web
📞 **Support :** @InvestCryptoPro_Support
    """
    await update.message.reply_text(message, parse_mode='Markdown')

def create_bot_application():
    """Créer l'application bot"""
    if not TELEGRAM_BOT_TOKEN:
        print("❌ Token Telegram manquant")
        return None
    
    try:
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        
        # Ajouter les handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        
        print("✅ Bot Telegram configuré avec succès")
        return application
        
    except Exception as e:
        print(f"❌ Erreur configuration bot: {e}")
        return None

async def run_bot():
    """Démarrer le bot"""
    application = create_bot_application()
    if not application:
        return False
    
    try:
        print("🚀 Démarrage du bot Telegram...")
        await application.initialize()
        await application.start()
        await application.updater.start_polling(drop_pending_updates=True)
        print("✅ Bot Telegram démarré avec succès!")
        
        # Maintenir le bot en vie
        stop_event = asyncio.Event()
        try:
            await stop_event.wait()
        except (KeyboardInterrupt, SystemExit):
            stop_event.set()
            
        return True
        
    except Exception as e:
        print(f"❌ Erreur bot: {e}")
        return False
    finally:
        try:
            await application.updater.stop()
            await application.stop()
            print("🛑 Bot arrêté")
        except:
            pass

if __name__ == "__main__":
    asyncio.run(run_bot())
