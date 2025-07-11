
import logging
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import asyncio
import os
from datetime import datetime, timedelta
import hashlib
import secrets
from werkzeug.security import generate_password_hash, check_password_hash
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import atexit

# Configuration
TELEGRAM_BOT_TOKEN = "7703189686:AAGArcOUnZImdOUTkwBggcyI9QSk5GSAB10"
DATABASE = 'telegram_bot.db'

# États de conversation
REGISTER_EMAIL, REGISTER_PASSWORD, REGISTER_FIRSTNAME, REGISTER_LASTNAME, REGISTER_REFERRAL = range(5)
LOGIN_EMAIL, LOGIN_PASSWORD = range(2)
DEPOSIT_AMOUNT, DEPOSIT_HASH = range(2)
WITHDRAW_AMOUNT, WITHDRAW_ADDRESS = range(2)
INVEST_ROI_AMOUNT, INVEST_STAKING_AMOUNT, INVEST_PROJECT_AMOUNT, INVEST_FROZEN_AMOUNT = range(4)

# Configuration du logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def init_telegram_bot_db():
    """Initialise la base de données pour le bot Telegram"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Table des utilisateurs
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            email TEXT UNIQUE,
            password_hash TEXT,
            first_name TEXT NOT NULL,
            last_name TEXT,
            username TEXT,
            balance REAL DEFAULT 10.0,
            pending_balance REAL DEFAULT 0.0,
            kyc_status TEXT DEFAULT 'pending',
            referral_code TEXT UNIQUE,
            referred_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Plans ROI
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS roi_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            daily_rate REAL NOT NULL,
            duration_days INTEGER NOT NULL,
            min_amount REAL NOT NULL,
            max_amount REAL NOT NULL,
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Investissements utilisateurs
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_investments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            plan_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            start_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            end_date TIMESTAMP,
            daily_profit REAL NOT NULL,
            total_earned REAL DEFAULT 0.0,
            is_active BOOLEAN DEFAULT 1,
            transaction_hash TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (plan_id) REFERENCES roi_plans (id)
        )
    ''')

    # Projets crowdfunding
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            category TEXT NOT NULL,
            target_amount REAL NOT NULL,
            raised_amount REAL DEFAULT 0.0,
            expected_return REAL NOT NULL,
            duration_months INTEGER NOT NULL,
            min_investment REAL NOT NULL,
            max_investment REAL NOT NULL,
            status TEXT DEFAULT 'collecting',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deadline TIMESTAMP
        )
    ''')

    # Investissements projets
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS project_investments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            project_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            investment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            transaction_hash TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (project_id) REFERENCES projects (id)
        )
    ''')

    # Transactions
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            amount REAL NOT NULL,
            status TEXT DEFAULT 'pending',
            transaction_hash TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # Notifications
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            type TEXT NOT NULL,
            is_read BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # Plans de staking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS staking_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            duration_days INTEGER NOT NULL,
            annual_rate REAL NOT NULL,
            min_amount REAL NOT NULL,
            max_amount REAL NOT NULL,
            penalty_rate REAL DEFAULT 0.05,
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Staking utilisateurs
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_staking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            plan_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            start_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            end_date TIMESTAMP,
            is_active BOOLEAN DEFAULT 1,
            total_earned REAL DEFAULT 0.0,
            transaction_hash TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (plan_id) REFERENCES staking_plans (id)
        )
    ''')

    # Plans gelés
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS frozen_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            duration_days INTEGER NOT NULL,
            total_return_rate REAL NOT NULL,
            min_amount REAL NOT NULL,
            max_amount REAL NOT NULL,
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Investissements gelés
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_frozen_investments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            plan_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            start_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            end_date TIMESTAMP,
            final_amount REAL NOT NULL,
            is_active BOOLEAN DEFAULT 1,
            transaction_hash TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (plan_id) REFERENCES frozen_plans (id)
        )
    ''')

    # Insérer les plans par défaut
    cursor.execute('''
        INSERT OR IGNORE INTO roi_plans (name, description, daily_rate, duration_days, min_amount, max_amount)
        VALUES 
        ('Plan Débutant', 'Idéal pour débuter ! 5% par jour pendant 30 jours. Retour total de 150%.', 0.05, 30, 10, 1000),
        ('Plan Intermédiaire', 'Plan équilibré ! 8% par jour pendant 45 jours. Retour total de 360%.', 0.08, 45, 10, 5000),
        ('Plan Premium', 'CHOIX POPULAIRE ! 12% par jour pendant 60 jours. Retour total de 720%.', 0.12, 60, 10, 10000),
        ('Plan VIP', 'EXCLUSIF ! 15% par jour pendant 90 jours. Retour total de 1350%.', 0.15, 90, 10, 50000)
    ''')

    cursor.execute('''
        INSERT OR IGNORE INTO staking_plans (name, description, duration_days, annual_rate, min_amount, max_amount, penalty_rate)
        VALUES 
        ('Staking Flexible', 'Stakez 15 jours pour 12% par an. Flexibilité maximale !', 15, 0.12, 10, 5000, 0.03),
        ('Staking Standard', '30 jours pour 18% par an. Notre plan le plus populaire !', 30, 0.18, 10, 10000, 0.05),
        ('Staking Premium', '90 jours pour 25% par an. Pour les vrais HODLers !', 90, 0.25, 10, 25000, 0.08)
    ''')

    cursor.execute('''
        INSERT OR IGNORE INTO frozen_plans (name, description, duration_days, total_return_rate, min_amount, max_amount)
        VALUES 
        ('Plan Diamant', 'Investissement premium ! 6 mois pour 250% de retour GARANTI.', 180, 2.5, 10, 50000),
        ('Plan Platinum', 'L\'ÉLITE ! 12 mois pour 400% de retour total !', 365, 4.0, 10, 100000)
    ''')

    cursor.execute('''
        INSERT OR IGNORE INTO projects (title, description, category, target_amount, expected_return, duration_months, min_investment, max_investment, deadline)
        VALUES 
        ('Ferme Solaire Éco', 'Investissez dans la plus grande ferme solaire d\'Afrique ! 20% de retour garanti grâce aux contrats gouvernementaux.', 'Énergie', 50000, 0.20, 18, 10, 5000, datetime("now", "+60 days")),
        ('Immobilier Résidentiel', 'Complexe résidentiel de luxe. 25% de retour sur 24 mois grâce à la plus-value et aux loyers.', 'Immobilier', 100000, 0.25, 24, 10, 10000, datetime("now", "+90 days")),
        ('Agriculture Bio', 'Ferme bio moderne. 18% de retour en 12 mois grâce à la demande croissante pour le bio.', 'Agriculture', 30000, 0.18, 12, 10, 3000, datetime("now", "+45 days"))
    ''')

    conn.commit()
    conn.close()

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def generate_transaction_hash():
    return hashlib.sha256(f"{datetime.now().isoformat()}{secrets.token_hex(16)}".encode()).hexdigest()

def generate_referral_code():
    return secrets.token_urlsafe(8).upper()

def add_notification(user_id, title, message, type='info'):
    conn = get_db_connection()
    conn.execute('''
        INSERT INTO notifications (user_id, title, message, type)
        VALUES (?, ?, ?, ?)
    ''', (user_id, title, message, type))
    conn.commit()
    conn.close()

def get_user_by_telegram_id(telegram_id):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    conn.close()
    return user

def create_user_from_telegram(telegram_id, first_name, last_name=None, username=None):
    """Crée automatiquement un utilisateur depuis les infos Telegram"""
    conn = get_db_connection()
    
    referral_code = generate_referral_code()
    
    cursor = conn.execute('''
        INSERT INTO users (telegram_id, first_name, last_name, username, referral_code, balance)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (telegram_id, first_name, last_name or '', username or '', referral_code, 10.0))
    
    user_id = cursor.lastrowid
    conn.commit()
    
    # Ajouter notification de bienvenue
    add_notification(
        user_id,
        'Bienvenue sur InvestCrypto Pro !',
        'Votre compte a été créé ! Vous avez reçu 10 USDT de bonus de bienvenue !',
        'success'
    )
    
    # Récupérer l'utilisateur créé
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    return user

# === COMMANDES PRINCIPALES ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /start - Menu principal avec création automatique d'utilisateur"""
    telegram_user = update.effective_user
    
    # Obtenir ou créer l'utilisateur
    user = get_user_by_telegram_id(telegram_user.id)
    
    if not user:
        user = create_user_from_telegram(
            telegram_user.id,
            telegram_user.first_name,
            telegram_user.last_name,
            telegram_user.username
        )
    
    if user:
        await show_main_menu(update, context, user)
    else:
        await update.message.reply_text(
            "❌ Erreur lors de la création de votre compte. Veuillez réessayer.",
            parse_mode='Markdown'
        )

async def show_main_menu(update, context, user):
    """Affiche le menu principal"""
    keyboard = [
        [InlineKeyboardButton("💰 Mon portefeuille", callback_data="wallet")],
        [InlineKeyboardButton("📈 Plans ROI", callback_data="roi_plans"),
         InlineKeyboardButton("🎯 Projets", callback_data="projects")],
        [InlineKeyboardButton("💎 Staking", callback_data="staking_plans"),
         InlineKeyboardButton("🧊 Plans gelés", callback_data="frozen_plans")],
        [InlineKeyboardButton("💳 Dépôt", callback_data="deposit"),
         InlineKeyboardButton("💸 Retrait", callback_data="withdraw")],
        [InlineKeyboardButton("📊 Mes investissements", callback_data="my_investments")],
        [InlineKeyboardButton("👥 Parrainage", callback_data="referral"),
         InlineKeyboardButton("🔔 Notifications", callback_data="notifications")],
        [InlineKeyboardButton("👤 Profil", callback_data="profile"),
         InlineKeyboardButton("❓ Aide", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Calcul des statistiques
    conn = get_db_connection()
    
    total_invested = conn.execute('''
        SELECT COALESCE(SUM(amount), 0) as total 
        FROM user_investments 
        WHERE user_id = ? AND is_active = 1
    ''', (user['id'],)).fetchone()['total']

    total_earned = conn.execute('''
        SELECT COALESCE(SUM(total_earned), 0) as total 
        FROM user_investments 
        WHERE user_id = ?
    ''', (user['id'],)).fetchone()['total']

    unread_notifications = conn.execute('''
        SELECT COUNT(*) as count 
        FROM notifications 
        WHERE user_id = ? AND is_read = 0
    ''', (user['id'],)).fetchone()['count']

    conn.close()

    message = f"""
🏛️ **INVESTCRYPTO PRO - DASHBOARD**

👋 Salut {user['first_name']} !

💰 **Solde disponible :** {user['balance']:.2f} USDT
📈 **Total investi :** {total_invested:.2f} USDT
🎯 **Gains totaux :** {total_earned:.2f} USDT
💼 **Valeur portfolio :** {(user['balance'] + total_invested):.2f} USDT

📊 **Statut KYC :** {user['kyc_status']}
🎁 **Code parrain :** `{user['referral_code']}`
🔔 **Notifications :** {unread_notifications} non lues

⏰ **Dernière connexion :** {datetime.now().strftime('%d/%m/%Y %H:%M')}

🚀 Que souhaitez-vous faire aujourd'hui ?
    """

    if hasattr(update, 'message') and update.message:
        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

# === GESTION DU PORTEFEUILLE ===

async def show_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Afficher le portefeuille détaillé"""
    await update.callback_query.answer()
    user = get_user_by_telegram_id(update.effective_user.id)

    conn = get_db_connection()

    # Statistiques des investissements
    roi_stats = conn.execute('''
        SELECT COUNT(*) as count, COALESCE(SUM(amount), 0) as total, COALESCE(SUM(total_earned), 0) as earned
        FROM user_investments 
        WHERE user_id = ? AND is_active = 1
    ''', (user['id'],)).fetchone()

    project_stats = conn.execute('''
        SELECT COUNT(*) as count, COALESCE(SUM(amount), 0) as total
        FROM project_investments 
        WHERE user_id = ?
    ''', (user['id'],)).fetchone()

    staking_stats = conn.execute('''
        SELECT COUNT(*) as count, COALESCE(SUM(amount), 0) as total
        FROM user_staking 
        WHERE user_id = ? AND is_active = 1
    ''', (user['id'],)).fetchone()

    frozen_stats = conn.execute('''
        SELECT COUNT(*) as count, COALESCE(SUM(amount), 0) as total
        FROM user_frozen_investments 
        WHERE user_id = ? AND is_active = 1
    ''', (user['id'],)).fetchone()

    recent_transactions = conn.execute('''
        SELECT type, amount, status, created_at
        FROM transactions 
        WHERE user_id = ? 
        ORDER BY created_at DESC 
        LIMIT 3
    ''', (user['id'],)).fetchall()

    conn.close()

    keyboard = [
        [InlineKeyboardButton("💳 Effectuer un dépôt", callback_data="deposit")],
        [InlineKeyboardButton("💸 Effectuer un retrait", callback_data="withdraw")],
        [InlineKeyboardButton("🔙 Menu principal", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    total_portfolio = (user['balance'] + roi_stats['total'] + project_stats['total'] + 
                      staking_stats['total'] + frozen_stats['total'])

    transactions_text = ""
    if recent_transactions:
        transactions_text = "\n📋 **Dernières transactions :**\n"
        for tx in recent_transactions:
            status_emoji = "✅" if tx['status'] == 'completed' else "⏳" if tx['status'] == 'pending' else "❌"
            type_emoji = "📥" if tx['type'] == 'deposit' else "📤" if tx['type'] == 'withdrawal' else "💎"
            transactions_text += f"{status_emoji} {type_emoji} {tx['amount']:.2f} USDT\n"

    message = f"""
💰 **MON PORTEFEUILLE**

💵 **Solde disponible :** {user['balance']:.2f} USDT
💎 **Solde en attente :** {user['pending_balance']:.2f} USDT

📈 **RÉPARTITION DE MES INVESTISSEMENTS :**

🎯 **Plans ROI :** {roi_stats['count']} actifs
   💰 Montant : {roi_stats['total']:.2f} USDT
   🎁 Gains : {roi_stats['earned']:.2f} USDT

🎯 **Projets :** {project_stats['count']} investissements
   💰 Montant : {project_stats['total']:.2f} USDT

🎯 **Staking :** {staking_stats['count']} positions
   💰 Montant : {staking_stats['total']:.2f} USDT

🎯 **Plans gelés :** {frozen_stats['count']} positions
   💰 Montant : {frozen_stats['total']:.2f} USDT

💼 **VALEUR TOTALE DU PORTFOLIO :** {total_portfolio:.2f} USDT
{transactions_text}
    """

    await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

# === PLANS ROI ===

async def show_roi_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Afficher les plans ROI"""
    await update.callback_query.answer()

    conn = get_db_connection()
    plans = conn.execute('SELECT * FROM roi_plans WHERE is_active = 1').fetchall()
    conn.close()

    keyboard = []
    message = "📈 **PLANS D'INVESTISSEMENT ROI**\n\n"

    for plan in plans:
        total_return = (plan['daily_rate'] * plan['duration_days']) * 100
        emoji = "🥉" if plan['daily_rate'] <= 0.05 else "🥈" if plan['daily_rate'] <= 0.08 else "🥇" if plan['daily_rate'] <= 0.12 else "👑"

        message += f"""
{emoji} **{plan['name'].upper()}**
📊 **{plan['daily_rate']*100:.1f}% par jour** pendant {plan['duration_days']} jours
💰 **{plan['min_amount']:.0f} - {plan['max_amount']:.0f} USDT**
🎯 **Retour total : {total_return:.0f}%**

{plan['description']}

"""
        keyboard.append([InlineKeyboardButton(f"{emoji} Investir - {plan['name']}", callback_data=f"invest_roi_{plan['id']}")])

    keyboard.append([InlineKeyboardButton("🔙 Menu principal", callback_data="main_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def invest_roi_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Début investissement ROI"""
    await update.callback_query.answer()
    plan_id = update.callback_query.data.split('_')[-1]

    conn = get_db_connection()
    plan = conn.execute('SELECT * FROM roi_plans WHERE id = ?', (plan_id,)).fetchone()
    user = get_user_by_telegram_id(update.effective_user.id)
    conn.close()

    if not plan:
        await update.callback_query.edit_message_text("❌ Plan non trouvé.")
        return

    context.user_data['invest_roi_plan_id'] = plan_id

    total_return = (plan['daily_rate'] * plan['duration_days']) * 100
    example_amount = 100
    example_daily = example_amount * plan['daily_rate']
    example_total = example_amount * (1 + plan['daily_rate'] * plan['duration_days'])

    message = f"""
💎 **INVESTISSEMENT - {plan['name'].upper()}**

📈 **Rendement :** {plan['daily_rate']*100:.1f}% par jour
⏰ **Durée :** {plan['duration_days']} jours
💰 **Limites :** {plan['min_amount']:.0f} - {plan['max_amount']:.0f} USDT
🎯 **Retour total :** {total_return:.0f}%

💡 **Exemple avec 100 USDT :**
• Profit quotidien : {example_daily:.2f} USDT
• Total reçu : {example_total:.2f} USDT
• Profit net : {example_total - example_amount:.2f} USDT

💼 **Votre solde :** {user['balance']:.2f} USDT

💵 **Entrez le montant à investir (en USDT) :**
    """

    await update.callback_query.edit_message_text(message, parse_mode='Markdown')
    return INVEST_ROI_AMOUNT

async def invest_roi_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Finaliser investissement ROI"""
    try:
        amount = float(update.message.text)
    except ValueError:
        await update.message.reply_text("❌ Montant invalide. Entrez un nombre valide.")
        return INVEST_ROI_AMOUNT

    plan_id = context.user_data['invest_roi_plan_id']
    user = get_user_by_telegram_id(update.effective_user.id)

    conn = get_db_connection()
    plan = conn.execute('SELECT * FROM roi_plans WHERE id = ?', (plan_id,)).fetchone()

    if not plan:
        await update.message.reply_text("❌ Plan non trouvé.")
        return ConversationHandler.END

    # Vérifications
    if amount < plan['min_amount'] or amount > plan['max_amount']:
        await update.message.reply_text(
            f"❌ Montant doit être entre {plan['min_amount']:.0f} et {plan['max_amount']:.0f} USDT.\n\n"
            "Entrez un montant valide :"
        )
        return INVEST_ROI_AMOUNT

    if user['balance'] < amount:
        await update.message.reply_text(
            f"❌ Solde insuffisant.\n\n"
            f"💰 Solde disponible : {user['balance']:.2f} USDT\n"
            f"💳 Montant requis : {amount:.2f} USDT\n\n"
            "Effectuez un dépôt ou choisissez un montant plus petit."
        )
        return ConversationHandler.END

    # Créer l'investissement
    start_date = datetime.now()
    end_date = start_date + timedelta(days=plan['duration_days'])
    daily_profit = amount * plan['daily_rate']
    total_expected = amount + (daily_profit * plan['duration_days'])

    conn.execute('''
        INSERT INTO user_investments (user_id, plan_id, amount, start_date, end_date, daily_profit, transaction_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (user['id'], plan_id, amount, start_date, end_date, daily_profit, generate_transaction_hash()))

    conn.execute('UPDATE users SET balance = balance - ? WHERE id = ?', (amount, user['id']))

    conn.execute('''
        INSERT INTO transactions (user_id, type, amount, status, transaction_hash)
        VALUES (?, 'investment', ?, 'completed', ?)
    ''', (user['id'], amount, generate_transaction_hash()))

    conn.commit()
    conn.close()

    add_notification(
        user['id'],
        'Nouvel investissement ROI',
        f'Investissement de {amount:.2f} USDT dans le plan {plan["name"]} activé avec succès.',
        'success'
    )

    context.user_data.clear()

    await update.message.reply_text(
        f"""
🎉 **INVESTISSEMENT RÉUSSI !**

💎 **Plan :** {plan['name']}
💰 **Montant investi :** {amount:.2f} USDT
📈 **Profit quotidien :** {daily_profit:.2f} USDT
📅 **Fin d'investissement :** {end_date.strftime('%d/%m/%Y')}
🎯 **Total attendu :** {total_expected:.2f} USDT

✅ **Votre investissement est maintenant actif !**
💡 **Les profits seront crédités automatiquement chaque jour.**

Utilisez /start pour retourner au menu principal.
        """,
        parse_mode='Markdown'
    )

    return ConversationHandler.END

# === SYSTÈME DE DÉPÔT ===

async def deposit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Début du processus de dépôt"""
    await update.callback_query.answer()

    message = f"""
💳 **EFFECTUER UN DÉPÔT**

🔹 **Adresse de dépôt USDT (TRC20) :**
`TYDzsYUEpvnYmQk4zGP9sWWcTEd2MiAtW6`

📋 **Instructions importantes :**
1. Envoyez uniquement des USDT à cette adresse
2. Utilisez exclusivement le réseau TRC20
3. Montant minimum : 10 USDT
4. Conservez le hash de transaction
5. Vérification sous 24h maximum

💰 **Entrez le montant déposé (en USDT) :**
    """

    await update.callback_query.edit_message_text(message, parse_mode='Markdown')
    return DEPOSIT_AMOUNT

async def deposit_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Récupérer le montant de dépôt"""
    try:
        amount = float(update.message.text)
    except ValueError:
        await update.message.reply_text("❌ Montant invalide. Entrez un nombre valide.")
        return DEPOSIT_AMOUNT

    if amount < 10:
        await update.message.reply_text(
            "❌ Montant minimum de dépôt : 10 USDT\n\n"
            "Entrez un montant supérieur ou égal à 10 USDT :"
        )
        return DEPOSIT_AMOUNT

    context.user_data['deposit_amount'] = amount

    await update.message.reply_text(
        f"""
✅ **Montant enregistré : {amount:.2f} USDT**

🔗 **Maintenant, entrez le hash de la transaction :**

💡 **Comment trouver le hash :**
• Dans votre wallet, allez dans l'historique
• Cliquez sur la transaction d'envoi
• Copiez le "Transaction ID" ou "Hash"
        """,
        parse_mode='Markdown'
    )
    return DEPOSIT_HASH

async def deposit_hash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Finaliser le dépôt"""
    transaction_hash = update.message.text.strip()
    amount = context.user_data['deposit_amount']
    user = get_user_by_telegram_id(update.effective_user.id)

    if len(transaction_hash) < 30:
        await update.message.reply_text(
            "❌ Hash de transaction invalide.\n\n"
            "Le hash doit contenir au moins 30 caractères.\n"
            "Vérifiez et entrez le hash correct :"
        )
        return DEPOSIT_HASH

    conn = get_db_connection()

    # Vérifier si le hash n'existe pas déjà
    existing_hash = conn.execute(
        'SELECT id FROM transactions WHERE transaction_hash = ?', 
        (transaction_hash,)
    ).fetchone()

    if existing_hash:
        conn.close()
        await update.message.reply_text(
            "❌ Ce hash de transaction a déjà été utilisé.\n\n"
            "Entrez un hash différent :"
        )
        return DEPOSIT_HASH

    # Créer la transaction en attente
    cursor = conn.execute('''
        INSERT INTO transactions (user_id, type, amount, status, transaction_hash)
        VALUES (?, 'deposit', ?, 'pending', ?)
    ''', (user['id'], amount, transaction_hash))

    deposit_id = cursor.lastrowid
    conn.commit()
    conn.close()

    add_notification(
        user['id'],
        'Dépôt en cours de vérification',
        f'Votre dépôt de {amount} USDT est en cours de vérification.',
        'info'
    )

    context.user_data.clear()

    await update.message.reply_text(
        f"""
✅ **DÉPÔT SOUMIS AVEC SUCCÈS**

💰 **Montant :** {amount:.2f} USDT
🔗 **Hash :** `{transaction_hash}`
🆔 **Référence :** #{deposit_id}

⏰ **Traitement :** Sous 24h maximum
🔔 **Notification :** Vous serez averti par message

Utilisez /start pour retourner au menu principal.
        """,
        parse_mode='Markdown'
    )

    return ConversationHandler.END

# === SYSTÈME DE RETRAIT ===

async def withdraw_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Début du processus de retrait"""
    await update.callback_query.answer()
    user = get_user_by_telegram_id(update.effective_user.id)

    if user['balance'] < 10:
        keyboard = [[InlineKeyboardButton("🔙 Menu principal", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.callback_query.edit_message_text(
            f"""
💸 **RETRAIT NON DISPONIBLE**

💰 **Solde actuel :** {user['balance']:.2f} USDT
💵 **Minimum requis :** 10 USDT

❌ **Solde insuffisant pour effectuer un retrait.**
            """,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return

    message = f"""
💸 **EFFECTUER UN RETRAIT**

💰 **Solde disponible :** {user['balance']:.2f} USDT
💵 **Montant minimum :** 10 USDT
💸 **Frais de retrait :** 2 USDT

🏦 **Détails du traitement :**
• Réseau : USDT TRC20 uniquement
• Délai : 24h maximum

💰 **Entrez le montant à retirer (en USDT) :**
    """

    await update.callback_query.edit_message_text(message, parse_mode='Markdown')
    return WITHDRAW_AMOUNT

async def withdraw_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Récupérer le montant de retrait"""
    try:
        amount = float(update.message.text)
    except ValueError:
        await update.message.reply_text("❌ Montant invalide. Entrez un nombre valide.")
        return WITHDRAW_AMOUNT

    user = get_user_by_telegram_id(update.effective_user.id)

    if amount < 10:
        await update.message.reply_text(
            "❌ Montant minimum de retrait : 10 USDT\n\n"
            "Entrez un montant supérieur ou égal à 10 USDT :"
        )
        return WITHDRAW_AMOUNT

    if amount > user['balance']:
        await update.message.reply_text(
            f"❌ Solde insuffisant.\n\n"
            f"💰 Solde disponible : {user['balance']:.2f} USDT\n"
            f"💸 Montant demandé : {amount:.2f} USDT\n\n"
            "Entrez un montant valide :"
        )
        return WITHDRAW_AMOUNT

    context.user_data['withdraw_amount'] = amount
    net_amount = amount - 2

    await update.message.reply_text(
        f"""
✅ **Montant de retrait : {amount:.2f} USDT**
💵 **Montant net (après frais) : {net_amount:.2f} USDT**

📍 **Entrez votre adresse USDT TRC20 :**

💡 **Format d'adresse TRC20 :**
• Commence par 'T'
• Contient 34 caractères
        """,
        parse_mode='Markdown'
    )
    return WITHDRAW_ADDRESS

async def withdraw_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Finaliser le retrait"""
    address = update.message.text.strip()
    amount = context.user_data['withdraw_amount']
    user = get_user_by_telegram_id(update.effective_user.id)

    # Validation de l'adresse TRC20
    if not address.startswith('T') or len(address) != 34:
        await update.message.reply_text(
            "❌ Adresse USDT TRC20 invalide.\n\n"
            "Vérifiez et entrez une adresse valide :"
        )
        return WITHDRAW_ADDRESS

    conn = get_db_connection()

    # Débiter le solde
    conn.execute('UPDATE users SET balance = balance - ? WHERE id = ?', (amount, user['id']))

    # Créer la transaction en attente
    cursor = conn.execute('''
        INSERT INTO transactions (user_id, type, amount, status, transaction_hash)
        VALUES (?, 'withdrawal', ?, 'pending', ?)
    ''', (user['id'], amount, f"{address}|{amount}"))

    withdrawal_id = cursor.lastrowid
    conn.commit()
    conn.close()

    add_notification(
        user['id'],
        'Retrait en cours de traitement',
        f'Votre retrait de {amount} USDT est en cours de traitement.',
        'info'
    )

    context.user_data.clear()
    net_amount = amount - 2

    await update.message.reply_text(
        f"""
✅ **RETRAIT CONFIRMÉ**

💰 **Montant :** {amount:.2f} USDT
💵 **Net (après frais) :** {net_amount:.2f} USDT
📍 **Adresse :** `{address}`
🆔 **Référence :** #{withdrawal_id}

⏰ **Traitement :** Sous 24h maximum

Utilisez /start pour retourner au menu.
        """,
        parse_mode='Markdown'
    )

    return ConversationHandler.END

# === AUTRES FONCTIONS ===

async def show_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Afficher les notifications"""
    user = get_user_by_telegram_id(update.effective_user.id)

    conn = get_db_connection()
    notifications = conn.execute('''
        SELECT * FROM notifications 
        WHERE user_id = ? 
        ORDER BY created_at DESC 
        LIMIT 10
    ''', (user['id'],)).fetchall()

    # Marquer comme lues
    conn.execute('UPDATE notifications SET is_read = 1 WHERE user_id = ?', (user['id'],))
    conn.commit()
    conn.close()

    keyboard = [[InlineKeyboardButton("🔙 Menu principal", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message = "🔔 **MES NOTIFICATIONS**\n\n"

    if notifications:
        for notif in notifications:
            type_emoji = "✅" if notif['type'] == 'success' else "⚠️" if notif['type'] == 'warning' else "❌" if notif['type'] == 'error' else "ℹ️"
            date_str = datetime.fromisoformat(notif['created_at'].replace('Z', '+00:00')).strftime('%d/%m %H:%M')
            message += f"{type_emoji} **{notif['title']}**\n"
            message += f"📝 {notif['message']}\n"
            message += f"📅 {date_str}\n\n"
    else:
        message += "😔 Aucune notification pour le moment."

    await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Afficher le profil utilisateur"""
    user = get_user_by_telegram_id(update.effective_user.id)

    keyboard = [[InlineKeyboardButton("🔙 Menu principal", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message = f"""
👤 **MON PROFIL**

**Informations :**
• Nom : {user['first_name']} {user['last_name'] or ''}
• Inscription : {datetime.fromisoformat(user['created_at'].replace('Z', '+00:00')).strftime('%d/%m/%Y')}

**Statut compte :**
• Solde : {user['balance']:.2f} USDT
• KYC : {user['kyc_status']}

**Parrainage :**
• Code : `{user['referral_code']}`
    """

    await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Afficher l'aide"""
    keyboard = [[InlineKeyboardButton("🔙 Menu principal", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message = """
❓ **CENTRE D'AIDE**

🚀 **Comment commencer :**
1. Effectuez votre premier dépôt (min. 10 USDT)
2. Choisissez un plan d'investissement
3. Regardez vos profits grandir !

💡 **Questions fréquentes :**

**Q: Quand reçois-je mes profits ?**
R: Les profits ROI sont crédités automatiquement chaque jour.

**Q: Puis-je retirer à tout moment ?**
R: Oui, votre solde disponible peut être retiré 24h/24.

**Q: Y a-t-il des frais ?**
R: Seuls 2 USDT de frais s'appliquent aux retraits.

📞 **Support :** @InvestCryptoPro_Support
    """

    await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

# === GESTION DES CALLBACKS ===

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestionnaire principal des callbacks"""
    query = update.callback_query
    await query.answer()

    data = query.data
    user = get_user_by_telegram_id(update.effective_user.id)

    if data == "main_menu":
        await start(update, context)
    elif data == "wallet":
        await show_wallet(update, context)
    elif data == "roi_plans":
        await show_roi_plans(update, context)
    elif data == "notifications":
        await show_notifications(update, context)
    elif data == "profile":
        await show_profile(update, context)
    elif data == "help":
        await show_help(update, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Annuler une conversation"""
    context.user_data.clear()
    await update.message.reply_text(
        "❌ **Opération annulée**\n\n"
        "Utilisez /start pour retourner au menu principal.",
        parse_mode='Markdown'
    )
    return ConversationHandler.END

# === TÂCHES PROGRAMMÉES ===

async def calculate_daily_profits():
    """Calculer les profits quotidiens"""
    conn = get_db_connection()
    active_investments = conn.execute('''
        SELECT ui.*, u.first_name
        FROM user_investments ui
        JOIN users u ON ui.user_id = u.id
        WHERE ui.is_active = 1 AND ui.end_date > datetime('now')
    ''').fetchall()

    for investment in active_investments:
        daily_profit = investment['daily_profit']

        # Mettre à jour le solde utilisateur
        conn.execute('''
            UPDATE users 
            SET balance = balance + ? 
            WHERE id = ?
        ''', (daily_profit, investment['user_id']))

        # Mettre à jour les gains totaux
        conn.execute('''
            UPDATE user_investments 
            SET total_earned = total_earned + ? 
            WHERE id = ?
        ''', (daily_profit, investment['id']))

        # Ajouter transaction
        conn.execute('''
            INSERT INTO transactions (user_id, type, amount, status, transaction_hash)
            VALUES (?, 'daily_profit', ?, 'completed', ?)
        ''', (investment['user_id'], daily_profit, generate_transaction_hash()))

        # Ajouter notification
        add_notification(
            investment['user_id'],
            'Profit journalier reçu',
            f'Vous avez reçu {daily_profit:.2f} USDT de profit quotidien',
            'success'
        )

    # Vérifier les investissements terminés
    completed_investments = conn.execute('''
        SELECT * FROM user_investments 
        WHERE is_active = 1 AND end_date <= datetime('now')
    ''').fetchall()

    for investment in completed_investments:
        conn.execute('''
            UPDATE user_investments 
            SET is_active = 0 
            WHERE id = ?
        ''', (investment['id'],))

        add_notification(
            investment['user_id'],
            'Plan d\'investissement terminé',
            f'Votre plan d\'investissement est arrivé à terme. Total gagné: {investment["total_earned"]:.2f} USDT',
            'info'
        )

    conn.commit()
    conn.close()

# === CONFIGURATION ET DÉMARRAGE ===

async def main():
    """Fonction principale"""
    if not TELEGRAM_BOT_TOKEN:
        print("❌ Token de bot Telegram non configuré")
        return

    # Initialiser la base de données
    init_telegram_bot_db()

    # Créer l'application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Handlers de conversation pour les dépôts
    deposit_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(deposit_start, pattern="^deposit$")],
        states={
            DEPOSIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_amount)],
            DEPOSIT_HASH: [MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_hash)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        per_message=False
    )

    # Handlers de conversation pour les retraits
    withdraw_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(withdraw_start, pattern="^withdraw$")],
        states={
            WITHDRAW_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_amount)],
            WITHDRAW_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_address)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        per_message=False
    )

    # Handlers de conversation pour les investissements ROI
    invest_roi_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(invest_roi_start, pattern="^invest_roi_")],
        states={
            INVEST_ROI_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, invest_roi_amount)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        per_message=False
    )

    # Ajouter tous les handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(deposit_handler)
    application.add_handler(withdraw_handler)
    application.add_handler(invest_roi_handler)
    application.add_handler(CallbackQueryHandler(handle_callback))

    # Setup du scheduler pour les profits quotidiens
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        func=calculate_daily_profits,
        trigger="cron",
        hour=0,
        minute=0,
        id='daily_profits'
    )
    scheduler.start()

    try:
        print("🚀 Démarrage du bot Telegram indépendant...")
        await application.initialize()
        await application.start()
        await application.updater.start_polling(
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=True
        )
        print("✅ Bot Telegram démarré avec succès!")
        
        # Maintenir le bot en vie
        stop_event = asyncio.Event()
        
        try:
            await stop_event.wait()
        except (KeyboardInterrupt, SystemExit):
            stop_event.set()
        
    except Exception as e:
        logger.error(f"❌ Erreur bot: {e}")
        print(f"❌ Erreur bot: {e}")
    finally:
        try:
            scheduler.shutdown()
            await application.updater.stop()
            await application.stop()
            print("🛑 Bot arrêté")
        except:
            pass

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Arrêt du bot par l'utilisateur")
    except Exception as e:
        print(f"❌ Erreur fatale: {e}")
