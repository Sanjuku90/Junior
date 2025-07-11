
import logging
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import asyncio
import os
from datetime import datetime

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
ADMIN_CHAT_ID = os.getenv('ADMIN_CHAT_ID')  # ID du chat admin
DATABASE = 'investment_platform.db'

# Configuration du logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /start"""
    await update.message.reply_text('Bot de confirmation des transactions - InvestCrypto Pro')

async def send_deposit_confirmation(user_id, amount, transaction_hash, deposit_id):
    """Envoie une demande de confirmation de dépôt à l'admin"""
    if not TELEGRAM_BOT_TOKEN or not ADMIN_CHAT_ID:
        return False
    
    try:
        # Récupérer les infos utilisateur
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        conn.close()
        
        if not user:
            return False
        
        # Créer les boutons de confirmation
        keyboard = [
            [
                InlineKeyboardButton("✅ Approuver", callback_data=f"approve_deposit_{deposit_id}"),
                InlineKeyboardButton("❌ Rejeter", callback_data=f"reject_deposit_{deposit_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Message de confirmation
        message = f"""
🏦 **NOUVELLE DEMANDE DE DÉPÔT**

👤 **Utilisateur:** {user['first_name']} {user['last_name']}
📧 **Email:** {user['email']}
💰 **Montant:** {amount} USDT
🔗 **Hash de transaction:** `{transaction_hash}`
🆔 **ID Dépôt:** #{deposit_id}

⏰ **Date:** {datetime.now().strftime('%d/%m/%Y %H:%M')}
        """
        
        # Envoyer le message à l'admin
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        await application.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return True
        
    except Exception as e:
        logger.error(f"Erreur envoi confirmation dépôt: {e}")
        return False

async def send_withdrawal_confirmation(user_id, amount, withdrawal_address, withdrawal_id):
    """Envoie une demande de confirmation de retrait à l'admin"""
    if not TELEGRAM_BOT_TOKEN or not ADMIN_CHAT_ID:
        return False
    
    try:
        # Récupérer les infos utilisateur
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        conn.close()
        
        if not user:
            return False
        
        # Créer les boutons de confirmation
        keyboard = [
            [
                InlineKeyboardButton("✅ Approuver", callback_data=f"approve_withdrawal_{withdrawal_id}"),
                InlineKeyboardButton("❌ Rejeter", callback_data=f"reject_withdrawal_{withdrawal_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Message de confirmation
        net_amount = amount - 2  # Frais de 2 USDT
        message = f"""
💸 **NOUVELLE DEMANDE DE RETRAIT**

👤 **Utilisateur:** {user['first_name']} {user['last_name']}
📧 **Email:** {user['email']}
💰 **Montant demandé:** {amount} USDT
💵 **Montant net:** {net_amount} USDT (après frais)
📍 **Adresse:** `{withdrawal_address}`
🆔 **ID Retrait:** #{withdrawal_id}

⏰ **Date:** {datetime.now().strftime('%d/%m/%Y %H:%M')}
        """
        
        # Envoyer le message à l'admin
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        await application.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return True
        
    except Exception as e:
        logger.error(f"Erreur envoi confirmation retrait: {e}")
        return False

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère les callbacks des boutons"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    conn = get_db_connection()
    
    try:
        if data.startswith('approve_deposit_'):
            deposit_id = data.split('_')[-1]
            
            # Récupérer la transaction
            transaction = conn.execute('''
                SELECT * FROM transactions 
                WHERE id = ? AND type = 'deposit' AND status = 'pending'
            ''', (deposit_id,)).fetchone()
            
            if transaction:
                # Approuver le dépôt
                conn.execute('''
                    UPDATE transactions 
                    SET status = 'completed' 
                    WHERE id = ?
                ''', (deposit_id,))
                
                # Ajouter le montant au solde utilisateur
                conn.execute('''
                    UPDATE users 
                    SET balance = balance + ? 
                    WHERE id = ?
                ''', (transaction['amount'], transaction['user_id']))
                
                # Ajouter une notification
                conn.execute('''
                    INSERT INTO notifications (user_id, title, message, type)
                    VALUES (?, ?, ?, ?)
                ''', (transaction['user_id'], 'Dépôt confirmé', 
                     f'Votre dépôt de {transaction["amount"]} USDT a été confirmé et ajouté à votre solde.', 'success'))
                
                conn.commit()
                
                await query.edit_message_text(
                    text=f"✅ **DÉPÔT APPROUVÉ**\n\n{query.message.text}\n\n**Statut:** Confirmé par l'admin",
                    parse_mode='Markdown'
                )
            
        elif data.startswith('reject_deposit_'):
            deposit_id = data.split('_')[-1]
            
            # Rejeter le dépôt
            conn.execute('''
                UPDATE transactions 
                SET status = 'rejected' 
                WHERE id = ? AND type = 'deposit'
            ''', (deposit_id,))
            
            # Récupérer la transaction pour notification
            transaction = conn.execute('''
                SELECT * FROM transactions WHERE id = ?
            ''', (deposit_id,)).fetchone()
            
            if transaction:
                # Ajouter une notification
                conn.execute('''
                    INSERT INTO notifications (user_id, title, message, type)
                    VALUES (?, ?, ?, ?)
                ''', (transaction['user_id'], 'Dépôt rejeté', 
                     f'Votre dépôt de {transaction["amount"]} USDT a été rejeté. Contactez le support.', 'error'))
            
            conn.commit()
            
            await query.edit_message_text(
                text=f"❌ **DÉPÔT REJETÉ**\n\n{query.message.text}\n\n**Statut:** Rejeté par l'admin",
                parse_mode='Markdown'
            )
            
        elif data.startswith('approve_withdrawal_'):
            withdrawal_id = data.split('_')[-1]
            
            # Approuver le retrait
            conn.execute('''
                UPDATE transactions 
                SET status = 'completed' 
                WHERE id = ? AND type = 'withdrawal'
            ''', (withdrawal_id,))
            
            # Récupérer la transaction pour notification
            transaction = conn.execute('''
                SELECT * FROM transactions WHERE id = ?
            ''', (withdrawal_id,)).fetchone()
            
            if transaction:
                # Ajouter une notification
                conn.execute('''
                    INSERT INTO notifications (user_id, title, message, type)
                    VALUES (?, ?, ?, ?)
                ''', (transaction['user_id'], 'Retrait confirmé', 
                     f'Votre retrait de {transaction["amount"]} USDT a été traité et envoyé.', 'success'))
            
            conn.commit()
            
            await query.edit_message_text(
                text=f"✅ **RETRAIT APPROUVÉ**\n\n{query.message.text}\n\n**Statut:** Traité par l'admin",
                parse_mode='Markdown'
            )
            
        elif data.startswith('reject_withdrawal_'):
            withdrawal_id = data.split('_')[-1]
            
            # Récupérer la transaction
            transaction = conn.execute('''
                SELECT * FROM transactions 
                WHERE id = ? AND type = 'withdrawal'
            ''', (withdrawal_id,)).fetchone()
            
            if transaction:
                # Rejeter le retrait et rembourser le solde
                conn.execute('''
                    UPDATE transactions 
                    SET status = 'rejected' 
                    WHERE id = ?
                ''', (withdrawal_id,))
                
                conn.execute('''
                    UPDATE users 
                    SET balance = balance + ? 
                    WHERE id = ?
                ''', (transaction['amount'], transaction['user_id']))
                
                # Ajouter une notification
                conn.execute('''
                    INSERT INTO notifications (user_id, title, message, type)
                    VALUES (?, ?, ?, ?)
                ''', (transaction['user_id'], 'Retrait rejeté', 
                     f'Votre retrait de {transaction["amount"]} USDT a été rejeté. Le montant a été recrédité.', 'error'))
            
            conn.commit()
            
            await query.edit_message_text(
                text=f"❌ **RETRAIT REJETÉ**\n\n{query.message.text}\n\n**Statut:** Rejeté par l'admin",
                parse_mode='Markdown'
            )
    
    except Exception as e:
        logger.error(f"Erreur lors du traitement du callback: {e}")
        await query.edit_message_text("❌ Erreur lors du traitement de la demande.")
    
    finally:
        conn.close()

def setup_telegram_bot():
    """Configure et démarre le bot Telegram"""
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN non configuré")
        return None
    
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Ajouter les handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_callback))
    
    return application

# Fonctions utilitaires pour l'intégration
from datetime import datetime

def notify_deposit_request(user_id, amount, transaction_hash, deposit_id):
    """Fonction pour notifier une demande de dépôt"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(send_deposit_confirmation(user_id, amount, transaction_hash, deposit_id))
        loop.close()
        return True
    except Exception as e:
        logger.error(f"Erreur notification dépôt: {e}")
        return False

def notify_withdrawal_request(user_id, amount, withdrawal_address, withdrawal_id):
    """Fonction pour notifier une demande de retrait"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(send_withdrawal_confirmation(user_id, amount, withdrawal_address, withdrawal_id))
        loop.close()
        return True
    except Exception as e:
        logger.error(f"Erreur notification retrait: {e}")
        return False
