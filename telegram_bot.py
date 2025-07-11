import logging
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
import asyncio
import os
from datetime import datetime
import threading

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
ADMIN_CHAT_ID = os.getenv('ADMIN_CHAT_ID')
DATABASE = 'investment_platform.db'

# Configuration du logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Variable globale pour éviter les instances multiples
_bot_instance = None
_bot_running = False

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /start - Menu principal admin"""
    if str(update.effective_chat.id) != ADMIN_CHAT_ID:
        await update.message.reply_text('❌ Accès non autorisé')
        return

    keyboard = [
        [InlineKeyboardButton("📊 Statistiques", callback_data="admin_stats")],
        [InlineKeyboardButton("💰 Transactions en attente", callback_data="admin_pending_transactions")],
        [InlineKeyboardButton("👥 Gérer les utilisateurs", callback_data="admin_users")],
        [InlineKeyboardButton("🔍 Vérifications KYC", callback_data="admin_kyc")],
        [InlineKeyboardButton("📈 Plans d'investissement", callback_data="admin_plans")],
        [InlineKeyboardButton("🎯 Projets crowdfunding", callback_data="admin_projects")],
        [InlineKeyboardButton("📢 Envoyer notification", callback_data="admin_notifications")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🏛️ **PANNEAU D'ADMINISTRATION**\n\n"
        "Bienvenue dans le système d'administration InvestCrypto Pro.\n"
        "Choisissez une action :",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def send_deposit_confirmation(user_id, amount, transaction_hash, deposit_id):
    """Envoie une demande de confirmation de dépôt à l'admin"""
    if not TELEGRAM_BOT_TOKEN or not ADMIN_CHAT_ID:
        return False

    try:
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        conn.close()

        if not user:
            return False

        keyboard = [
            [
                InlineKeyboardButton("✅ Approuver", callback_data=f"approve_deposit_{deposit_id}"),
                InlineKeyboardButton("❌ Rejeter", callback_data=f"reject_deposit_{deposit_id}")
            ],
            [InlineKeyboardButton("👤 Voir profil", callback_data=f"view_user_{user_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        message = f"""
🏦 **NOUVELLE DEMANDE DE DÉPÔT**

👤 **Utilisateur:** {user['first_name']} {user['last_name']}
📧 **Email:** {user['email']}
💰 **Montant:** {amount} USDT
🔗 **Hash:** `{transaction_hash}`
🆔 **ID:** #{deposit_id}
💼 **Solde actuel:** {user['balance']:.2f} USDT

⏰ **Date:** {datetime.now().strftime('%d/%m/%Y %H:%M')}
        """

        global _bot_instance
        if _bot_instance:
            await _bot_instance.bot.send_message(
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
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        conn.close()

        if not user:
            return False

        keyboard = [
            [
                InlineKeyboardButton("✅ Approuver", callback_data=f"approve_withdrawal_{withdrawal_id}"),
                InlineKeyboardButton("❌ Rejeter", callback_data=f"reject_withdrawal_{withdrawal_id}")
            ],
            [InlineKeyboardButton("👤 Voir profil", callback_data=f"view_user_{user_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        net_amount = amount - 2
        message = f"""
💸 **NOUVELLE DEMANDE DE RETRAIT**

👤 **Utilisateur:** {user['first_name']} {user['last_name']}
📧 **Email:** {user['email']}
💰 **Montant:** {amount} USDT
💵 **Net:** {net_amount} USDT (après frais)
📍 **Adresse:** `{withdrawal_address}`
🆔 **ID:** #{withdrawal_id}
💼 **Solde actuel:** {user['balance']:.2f} USDT

⏰ **Date:** {datetime.now().strftime('%d/%m/%Y %H:%M')}
        """

        global _bot_instance
        if _bot_instance:
            await _bot_instance.bot.send_message(
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
    """Gère tous les callbacks des boutons"""
    query = update.callback_query
    await query.answer()

    if str(query.from_user.id) != ADMIN_CHAT_ID:
        await query.edit_message_text("❌ Accès non autorisé")
        return

    data = query.data
    conn = get_db_connection()

    try:
        # === STATISTIQUES ===
        if data == "admin_stats":
            stats = {
                'users': conn.execute('SELECT COUNT(*) as count FROM users').fetchone()['count'],
                'investments': conn.execute('SELECT COALESCE(SUM(amount), 0) as total FROM user_investments').fetchone()['total'],
                'projects': conn.execute('SELECT COUNT(*) as count FROM projects').fetchone()['count'],
                'pending_deposits': conn.execute('SELECT COUNT(*) as count FROM transactions WHERE type = "deposit" AND status = "pending"').fetchone()['count'],
                'pending_withdrawals': conn.execute('SELECT COUNT(*) as count FROM transactions WHERE type = "withdrawal" AND status = "pending"').fetchone()['count'],
                'total_balance': conn.execute('SELECT COALESCE(SUM(balance), 0) as total FROM users').fetchone()['total']
            }

            keyboard = [[InlineKeyboardButton("🔙 Menu principal", callback_data="back_to_main")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            message = f"""
📊 **STATISTIQUES DE LA PLATEFORME**

👥 **Utilisateurs:** {stats['users']}
💰 **Total investi:** {stats['investments']:.2f} USDT
🎯 **Projets actifs:** {stats['projects']}
💳 **Solde total:** {stats['total_balance']:.2f} USDT

⏳ **En attente:**
   • Dépôts: {stats['pending_deposits']}
   • Retraits: {stats['pending_withdrawals']}

⏰ **Mis à jour:** {datetime.now().strftime('%d/%m/%Y %H:%M')}
            """

            await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

        # === TRANSACTIONS EN ATTENTE ===
        elif data == "admin_pending_transactions":
            pending_deposits = conn.execute('''
                SELECT t.*, u.first_name, u.last_name, u.email
                FROM transactions t
                JOIN users u ON t.user_id = u.id
                WHERE t.type = 'deposit' AND t.status = 'pending'
                ORDER BY t.created_at DESC
                LIMIT 5
            ''').fetchall()

            pending_withdrawals = conn.execute('''
                SELECT t.*, u.first_name, u.last_name, u.email
                FROM transactions t
                JOIN users u ON t.user_id = u.id
                WHERE t.type = 'withdrawal' AND t.status = 'pending'
                ORDER BY t.created_at DESC
                LIMIT 5
            ''').fetchall()

            keyboard = []
            message = "💰 **TRANSACTIONS EN ATTENTE**\n\n"

            if pending_deposits:
                message += "📥 **DÉPÔTS:**\n"
                for dep in pending_deposits:
                    message += f"• {dep['first_name']} {dep['last_name']} - {dep['amount']} USDT\n"
                    keyboard.append([InlineKeyboardButton(f"✅ Dépôt #{dep['id']}", callback_data=f"approve_deposit_{dep['id']}"),
                                   InlineKeyboardButton(f"❌ Rejeter #{dep['id']}", callback_data=f"reject_deposit_{dep['id']}")])
            else:
                message += "📥 **DÉPÔTS:** Aucun en attente\n"

            message += "\n"

            if pending_withdrawals:
                message += "📤 **RETRAITS:**\n"
                for wit in pending_withdrawals:
                    message += f"• {wit['first_name']} {wit['last_name']} - {wit['amount']} USDT\n"
                    keyboard.append([InlineKeyboardButton(f"✅ Retrait #{wit['id']}", callback_data=f"approve_withdrawal_{wit['id']}"),
                                   InlineKeyboardButton(f"❌ Rejeter #{wit['id']}", callback_data=f"reject_withdrawal_{wit['id']}")])
            else:
                message += "📤 **RETRAITS:** Aucun en attente\n"

            keyboard.append([InlineKeyboardButton("🔙 Menu principal", callback_data="back_to_main")])
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

        # === GESTION UTILISATEURS ===
        elif data == "admin_users":
            recent_users = conn.execute('''
                SELECT * FROM users 
                ORDER BY created_at DESC 
                LIMIT 5
            ''').fetchall()

            keyboard = []
            message = "👥 **GESTION DES UTILISATEURS**\n\n"

            for user in recent_users:
                message += f"• {user['first_name']} {user['last_name']} ({user['email']}) - {user['balance']:.2f} USDT\n"
                keyboard.append([InlineKeyboardButton(f"👤 {user['first_name']}", callback_data=f"view_user_{user['id']}")])

            keyboard.append([InlineKeyboardButton("🔍 Rechercher utilisateur", callback_data="search_user")])
            keyboard.append([InlineKeyboardButton("🔙 Menu principal", callback_data="back_to_main")])
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

        # === APPROBATION/REJET DÉPÔTS ===
        elif data.startswith('approve_deposit_'):
            deposit_id = data.split('_')[-1]

            transaction = conn.execute('''
                SELECT * FROM transactions 
                WHERE id = ? AND type = 'deposit' AND status = 'pending'
            ''', (deposit_id,)).fetchone()

            if transaction:
                conn.execute('UPDATE transactions SET status = "completed" WHERE id = ?', (deposit_id,))
                conn.execute('UPDATE users SET balance = balance + ? WHERE id = ?', 
                           (transaction['amount'], transaction['user_id']))
                conn.execute('''
                    INSERT INTO notifications (user_id, title, message, type)
                    VALUES (?, ?, ?, ?)
                ''', (transaction['user_id'], 'Dépôt confirmé', 
                     f'Votre dépôt de {transaction["amount"]} USDT a été confirmé.', 'success'))

                conn.commit()

                await query.edit_message_text(
                    f"✅ **DÉPÔT APPROUVÉ**\n\n{query.message.text}\n\n**Statut:** Confirmé",
                    parse_mode='Markdown'
                )

        elif data.startswith('reject_deposit_'):
            deposit_id = data.split('_')[-1]

            transaction = conn.execute('SELECT * FROM transactions WHERE id = ?', (deposit_id,)).fetchone()

            if transaction:
                conn.execute('UPDATE transactions SET status = "rejected" WHERE id = ?', (deposit_id,))
                conn.execute('''
                    INSERT INTO notifications (user_id, title, message, type)
                    VALUES (?, ?, ?, ?)
                ''', (transaction['user_id'], 'Dépôt rejeté', 
                     f'Votre dépôt de {transaction["amount"]} USDT a été rejeté.', 'error'))

                conn.commit()

                await query.edit_message_text(
                    f"❌ **DÉPÔT REJETÉ**\n\n{query.message.text}\n\n**Statut:** Rejeté",
                    parse_mode='Markdown'
                )

        # === APPROBATION/REJET RETRAITS ===
        elif data.startswith('approve_withdrawal_'):
            withdrawal_id = data.split('_')[-1]

            transaction = conn.execute('SELECT * FROM transactions WHERE id = ?', (withdrawal_id,)).fetchone()

            if transaction:
                conn.execute('UPDATE transactions SET status = "completed" WHERE id = ?', (withdrawal_id,))
                conn.execute('''
                    INSERT INTO notifications (user_id, title, message, type)
                    VALUES (?, ?, ?, ?)
                ''', (transaction['user_id'], 'Retrait confirmé', 
                     f'Votre retrait de {transaction["amount"]} USDT a été traité.', 'success'))

                conn.commit()

                await query.edit_message_text(
                    f"✅ **RETRAIT APPROUVÉ**\n\n{query.message.text}\n\n**Statut:** Traité",
                    parse_mode='Markdown'
                )

        elif data.startswith('reject_withdrawal_'):
            withdrawal_id = data.split('_')[-1]

            transaction = conn.execute('SELECT * FROM transactions WHERE id = ?', (withdrawal_id,)).fetchone()

            if transaction:
                conn.execute('UPDATE transactions SET status = "rejected" WHERE id = ?', (withdrawal_id,))
                conn.execute('UPDATE users SET balance = balance + ? WHERE id = ?', 
                           (transaction['amount'], transaction['user_id']))
                conn.execute('''
                    INSERT INTO notifications (user_id, title, message, type)
                    VALUES (?, ?, ?, ?)
                ''', (transaction['user_id'], 'Retrait rejeté', 
                     f'Votre retrait de {transaction["amount"]} USDT a été rejeté. Montant recrédité.', 'error'))

                conn.commit()

                await query.edit_message_text(
                    f"❌ **RETRAIT REJETÉ**\n\n{query.message.text}\n\n**Statut:** Rejeté",
                    parse_mode='Markdown'
                )

        # === VOIR PROFIL UTILISATEUR ===
        elif data.startswith('view_user_'):
            user_id = data.split('_')[-1]

            user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()

            if user:
                investments = conn.execute('''
                    SELECT COUNT(*) as count, COALESCE(SUM(amount), 0) as total
                    FROM user_investments 
                    WHERE user_id = ?
                ''', (user_id,)).fetchone()

                keyboard = [
                    [InlineKeyboardButton(f"💰 Ajuster solde", callback_data=f"adjust_balance_{user_id}")],
                    [InlineKeyboardButton(f"🔒 Bloquer", callback_data=f"block_user_{user_id}"),
                     InlineKeyboardButton(f"✅ Débloquer", callback_data=f"unblock_user_{user_id}")],
                    [InlineKeyboardButton("🔙 Retour", callback_data="admin_users")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                message = f"""
👤 **PROFIL UTILISATEUR**

**Nom:** {user['first_name']} {user['last_name']}
**Email:** {user['email']}
**Solde:** {user['balance']:.2f} USDT
**KYC:** {user['kyc_status']}
**Inscrit:** {user['created_at']}

**Investissements:**
• Total: {investments['count']}
• Montant: {investments['total']:.2f} USDT

**Code parrain:** {user['referral_code'] or 'Aucun'}
**Parrainé par:** {user['referred_by'] or 'Aucun'}
                """

                await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

        # === RETOUR MENU PRINCIPAL ===
        elif data == "back_to_main":
            keyboard = [
                [InlineKeyboardButton("📊 Statistiques", callback_data="admin_stats")],
                [InlineKeyboardButton("💰 Transactions en attente", callback_data="admin_pending_transactions")],
                [InlineKeyboardButton("👥 Gérer les utilisateurs", callback_data="admin_users")],
                [InlineKeyboardButton("🔍 Vérifications KYC", callback_data="admin_kyc")],
                [InlineKeyboardButton("📈 Plans d'investissement", callback_data="admin_plans")],
                [InlineKeyboardButton("🎯 Projets crowdfunding", callback_data="admin_projects")],
                [InlineKeyboardButton("📢 Envoyer notification", callback_data="admin_notifications")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                "🏛️ **PANNEAU D'ADMINISTRATION**\n\n"
                "Choisissez une action :",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )

    except Exception as e:
        logger.error(f"Erreur lors du traitement du callback: {e}")
        await query.edit_message_text(f"❌ Erreur: {str(e)}")

    finally:
        conn.close()

def setup_telegram_bot():
    """Configure et démarre le bot Telegram (instance unique)"""
    global _bot_instance, _bot_running

    if not TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN non configuré")
        return None

    if _bot_running:
        logger.info("Bot Telegram déjà en cours d'exécution")
        return _bot_instance

    try:
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

        # Ajouter les handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CallbackQueryHandler(handle_callback))

        _bot_instance = application
        _bot_running = True

        return application
    except Exception as e:
        logger.error(f"Erreur lors de la configuration du bot: {e}")
        return None

def stop_telegram_bot():
    """Arrête le bot Telegram"""
    global _bot_instance, _bot_running
    _bot_running = False
    _bot_instance = None

# Fonctions utilitaires pour l'intégration
def notify_deposit_request(user_id, amount, transaction_hash, deposit_id):
    """Fonction pour notifier une demande de dépôt"""
    if not _bot_running:
        return False

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
    if not _bot_running:
        return False

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(send_withdrawal_confirmation(user_id, amount, withdrawal_address, withdrawal_id))
        loop.close()
        return True
    except Exception as e:
        logger.error(f"Erreur notification retrait: {e}")
        return False

#The start_bot function was not in the original code, adding it here.
async def start_bot():
    global telegram_app
    telegram_app = setup_telegram_bot()
    if telegram_app:
        try:
            await telegram_app.initialize()
            await telegram_app.start()
            await telegram_app.updater.start_polling(
                allowed_updates=["message", "callback_query"],
                drop_pending_updates=True  # Ignore les anciens messages
            )
            # Maintenir le bot actif avec la nouvelle API
            await telegram_app.updater.idle()
        except Exception as e:
            print(f"❌ Erreur bot polling: {e}")
        finally:
            await telegram_app.stop()