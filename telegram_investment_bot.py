
import logging
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import asyncio
import os
from datetime import datetime, timedelta
import hashlib
import secrets
import json
from werkzeug.security import generate_password_hash, check_password_hash

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN_USER')
DATABASE = 'investment_platform.db'

# États de conversation
REGISTER_EMAIL, REGISTER_PASSWORD, REGISTER_FIRSTNAME, REGISTER_LASTNAME, REGISTER_REFERRAL = range(5)
LOGIN_EMAIL, LOGIN_PASSWORD = range(2)
DEPOSIT_AMOUNT, DEPOSIT_HASH = range(2)
WITHDRAW_AMOUNT, WITHDRAW_ADDRESS = range(2)
INVEST_ROI_AMOUNT, INVEST_STAKING_AMOUNT, INVEST_PROJECT_AMOUNT = range(3)

# Configuration du logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

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

# Fonction pour obtenir l'utilisateur depuis Telegram ID
def get_user_by_telegram_id(telegram_id):
    conn = get_db_connection()
    
    # Vérifier d'abord si l'utilisateur existe avec telegram_id
    user = conn.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    
    if not user:
        # Si pas de telegram_id, chercher par email si l'utilisateur s'est connecté récemment
        conn.close()
        return None
    
    conn.close()
    return user

# Ajouter une colonne telegram_id à la table users si elle n'existe pas
def init_telegram_db():
    conn = get_db_connection()
    try:
        conn.execute('ALTER TABLE users ADD COLUMN telegram_id INTEGER UNIQUE')
        conn.commit()
    except sqlite3.OperationalError:
        # La colonne existe déjà
        pass
    conn.close()

# === COMMANDES PRINCIPALES ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /start - Menu principal"""
    user = get_user_by_telegram_id(update.effective_user.id)
    
    if not user:
        # Utilisateur non connecté
        keyboard = [
            [InlineKeyboardButton("🔐 Se connecter", callback_data="login")],
            [InlineKeyboardButton("📝 S'inscrire", callback_data="register")],
            [InlineKeyboardButton("ℹ️ À propos", callback_data="about")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🚀 **Bienvenue sur InvestCrypto Pro**\n\n"
            "💎 Plateforme d'investissement crypto sécurisée\n"
            "📈 Rendements garantis jusqu'à 15% par jour\n"
            "🔒 Technologie blockchain avancée\n\n"
            "Connectez-vous ou créez un compte pour commencer :",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        # Utilisateur connecté - Menu principal
        await show_main_menu(update, context, user)

async def show_main_menu(update, context, user):
    """Affiche le menu principal pour un utilisateur connecté"""
    keyboard = [
        [InlineKeyboardButton("💰 Mon portefeuille", callback_data="wallet")],
        [InlineKeyboardButton("📈 Plans ROI", callback_data="roi_plans"),
         InlineKeyboardButton("🎯 Projets", callback_data="projects")],
        [InlineKeyboardButton("💎 Staking", callback_data="staking_plans"),
         InlineKeyboardButton("🧊 Plans gelés", callback_data="frozen_plans")],
        [InlineKeyboardButton("💳 Dépôt", callback_data="deposit"),
         InlineKeyboardButton("💸 Retrait", callback_data="withdraw")],
        [InlineKeyboardButton("📊 Mes investissements", callback_data="my_investments")],
        [InlineKeyboardButton("👤 Profil", callback_data="profile"),
         InlineKeyboardButton("🔔 Notifications", callback_data="notifications")],
        [InlineKeyboardButton("❓ Aide", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = f"""
🏛️ **INVESTCRYPTO PRO - DASHBOARD**

👋 Bonjour {user['first_name']} {user['last_name']}!

💰 **Solde:** {user['balance']:.2f} USDT
📊 **Statut KYC:** {user['kyc_status']}
🎁 **Code parrain:** `{user['referral_code']}`

⏰ **Dernière connexion:** {datetime.now().strftime('%d/%m/%Y %H:%M')}
    """
    
    if hasattr(update, 'message') and update.message:
        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

# === SYSTÈME D'AUTHENTIFICATION ===

async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Début du processus d'inscription"""
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        "📝 **INSCRIPTION**\n\n"
        "Entrez votre adresse email :",
        parse_mode='Markdown'
    )
    return REGISTER_EMAIL

async def register_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Récupérer l'email pour l'inscription"""
    email = update.message.text.strip()
    
    # Vérifier si l'email existe déjà
    conn = get_db_connection()
    existing_user = conn.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
    conn.close()
    
    if existing_user:
        await update.message.reply_text(
            "❌ Cet email est déjà utilisé.\n\n"
            "Utilisez /start pour recommencer."
        )
        return ConversationHandler.END
    
    context.user_data['register_email'] = email
    await update.message.reply_text(
        "✅ Email enregistré!\n\n"
        "🔐 Maintenant, choisissez un mot de passe sécurisé :"
    )
    return REGISTER_PASSWORD

async def register_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Récupérer le mot de passe"""
    password = update.message.text
    
    if len(password) < 6:
        await update.message.reply_text(
            "❌ Le mot de passe doit contenir au moins 6 caractères.\n\n"
            "Veuillez réessayer :"
        )
        return REGISTER_PASSWORD
    
    context.user_data['register_password'] = password
    await update.message.reply_text(
        "✅ Mot de passe enregistré!\n\n"
        "👤 Entrez votre prénom :"
    )
    return REGISTER_FIRSTNAME

async def register_firstname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Récupérer le prénom"""
    context.user_data['register_firstname'] = update.message.text.strip()
    await update.message.reply_text(
        "✅ Prénom enregistré!\n\n"
        "👤 Entrez votre nom de famille :"
    )
    return REGISTER_LASTNAME

async def register_lastname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Récupérer le nom de famille"""
    context.user_data['register_lastname'] = update.message.text.strip()
    await update.message.reply_text(
        "✅ Nom enregistré!\n\n"
        "🎁 Avez-vous un code de parrainage? (Tapez 'non' pour ignorer)"
    )
    return REGISTER_REFERRAL

async def register_referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Finaliser l'inscription"""
    referral_code = update.message.text.strip()
    if referral_code.lower() == 'non':
        referral_code = ''
    
    # Créer l'utilisateur
    conn = get_db_connection()
    
    password_hash = generate_password_hash(context.user_data['register_password'])
    user_referral_code = generate_referral_code()
    
    cursor = conn.execute('''
        INSERT INTO users (email, password_hash, first_name, last_name, referral_code, referred_by, telegram_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        context.user_data['register_email'],
        password_hash,
        context.user_data['register_firstname'],
        context.user_data['register_lastname'],
        user_referral_code,
        referral_code,
        update.effective_user.id
    ))
    
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    # Nettoyer les données temporaires
    context.user_data.clear()
    
    await update.message.reply_text(
        "🎉 **INSCRIPTION RÉUSSIE!**\n\n"
        f"✅ Compte créé avec succès\n"
        f"🎁 Votre code parrain: `{user_referral_code}`\n\n"
        "Utilisez /start pour accéder à votre dashboard!"
    )
    
    return ConversationHandler.END

async def login_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Début du processus de connexion"""
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        "🔐 **CONNEXION**\n\n"
        "Entrez votre adresse email :",
        parse_mode='Markdown'
    )
    return LOGIN_EMAIL

async def login_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Récupérer l'email pour la connexion"""
    context.user_data['login_email'] = update.message.text.strip()
    await update.message.reply_text(
        "✅ Email reçu!\n\n"
        "🔐 Entrez votre mot de passe :"
    )
    return LOGIN_PASSWORD

async def login_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Finaliser la connexion"""
    email = context.user_data['login_email']
    password = update.message.text
    
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
    
    if user and check_password_hash(user['password_hash'], password):
        # Associer le Telegram ID à l'utilisateur
        conn.execute('UPDATE users SET telegram_id = ? WHERE id = ?', 
                    (update.effective_user.id, user['id']))
        conn.commit()
        conn.close()
        
        context.user_data.clear()
        
        await update.message.reply_text(
            "🎉 **CONNEXION RÉUSSIE!**\n\n"
            f"Bienvenue {user['first_name']}!\n\n"
            "Utilisez /start pour accéder à votre dashboard!"
        )
    else:
        conn.close()
        await update.message.reply_text(
            "❌ Email ou mot de passe incorrect.\n\n"
            "Utilisez /start pour recommencer."
        )
    
    return ConversationHandler.END

# === GESTION DU PORTEFEUILLE ===

async def show_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Afficher le portefeuille"""
    await update.callback_query.answer()
    user = get_user_by_telegram_id(update.effective_user.id)
    
    if not user:
        await update.callback_query.edit_message_text("❌ Veuillez vous connecter d'abord.")
        return
    
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
    
    conn.close()
    
    keyboard = [
        [InlineKeyboardButton("💳 Effectuer un dépôt", callback_data="deposit")],
        [InlineKeyboardButton("💸 Effectuer un retrait", callback_data="withdraw")],
        [InlineKeyboardButton("📊 Historique transactions", callback_data="transaction_history")],
        [InlineKeyboardButton("🔙 Menu principal", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = f"""
💰 **MON PORTEFEUILLE**

💵 **Solde disponible:** {user['balance']:.2f} USDT
💎 **Solde en attente:** {user['pending_balance']:.2f} USDT

📈 **MES INVESTISSEMENTS:**
• ROI Plans: {roi_stats['count']} ({roi_stats['total']:.2f} USDT)
  └ Gains: {roi_stats['earned']:.2f} USDT
• Projets: {project_stats['count']} ({project_stats['total']:.2f} USDT)
• Staking: {staking_stats['count']} ({staking_stats['total']:.2f} USDT)

💼 **Valeur totale:** {(user['balance'] + roi_stats['total'] + project_stats['total'] + staking_stats['total']):.2f} USDT
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
        message += f"""
**{plan['name']}**
📊 {plan['daily_rate']*100:.1f}% par jour pendant {plan['duration_days']} jours
💰 {plan['min_amount']:.0f} - {plan['max_amount']:.0f} USDT
🎯 Retour total: {total_return:.0f}%

{plan['description'][:100]}...

"""
        keyboard.append([InlineKeyboardButton(f"💎 Investir - {plan['name']}", callback_data=f"invest_roi_{plan['id']}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Menu principal", callback_data="main_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def invest_roi_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Début investissement ROI"""
    await update.callback_query.answer()
    plan_id = update.callback_query.data.split('_')[-1]
    
    conn = get_db_connection()
    plan = conn.execute('SELECT * FROM roi_plans WHERE id = ?', (plan_id,)).fetchone()
    conn.close()
    
    if not plan:
        await update.callback_query.edit_message_text("❌ Plan non trouvé.")
        return
    
    context.user_data['invest_roi_plan_id'] = plan_id
    
    message = f"""
💎 **INVESTISSEMENT - {plan['name'].upper()}**

📈 **Rendement:** {plan['daily_rate']*100:.1f}% par jour
⏰ **Durée:** {plan['duration_days']} jours
💰 **Limites:** {plan['min_amount']:.0f} - {plan['max_amount']:.0f} USDT
🎯 **Retour total:** {(plan['daily_rate'] * plan['duration_days'] * 100):.0f}%

💵 **Entrez le montant à investir (en USDT):**
    """
    
    await update.callback_query.edit_message_text(message, parse_mode='Markdown')
    return INVEST_ROI_AMOUNT

async def invest_roi_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Finaliser investissement ROI"""
    try:
        amount = float(update.message.text)
    except ValueError:
        await update.message.reply_text("❌ Montant invalide. Entrez un nombre.")
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
            f"❌ Montant doit être entre {plan['min_amount']:.0f} et {plan['max_amount']:.0f} USDT."
        )
        return INVEST_ROI_AMOUNT
    
    if user['balance'] < amount:
        await update.message.reply_text("❌ Solde insuffisant.")
        return ConversationHandler.END
    
    # Créer l'investissement
    start_date = datetime.now()
    end_date = start_date + timedelta(days=plan['duration_days'])
    daily_profit = amount * plan['daily_rate']
    
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
    
    context.user_data.clear()
    
    await update.message.reply_text(
        f"""
🎉 **INVESTISSEMENT RÉUSSI!**

💎 **Plan:** {plan['name']}
💰 **Montant:** {amount:.2f} USDT
📈 **Profit quotidien:** {daily_profit:.2f} USDT
⏰ **Fin:** {end_date.strftime('%d/%m/%Y')}

✅ Votre investissement est maintenant actif!

Utilisez /start pour retourner au menu.
        """,
        parse_mode='Markdown'
    )
    
    return ConversationHandler.END

# === PROJETS CROWDFUNDING ===

async def show_projects(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Afficher les projets"""
    await update.callback_query.answer()
    
    conn = get_db_connection()
    projects = conn.execute('''
        SELECT *, 
               (raised_amount * 100.0 / target_amount) as progress_percent
        FROM projects 
        WHERE status = 'collecting' AND deadline > datetime('now')
        ORDER BY created_at DESC
        LIMIT 5
    ''').fetchall()
    conn.close()
    
    keyboard = []
    message = "🎯 **PROJETS DE CROWDFUNDING**\n\n"
    
    for project in projects:
        message += f"""
**{project['title']}**
📊 Progression: {project['progress_percent']:.1f}%
💰 {project['raised_amount']:.0f} / {project['target_amount']:.0f} USDT
📈 Retour attendu: {project['expected_return']*100:.0f}%
⏰ Durée: {project['duration_months']} mois
💵 {project['min_investment']:.0f} - {project['max_investment']:.0f} USDT

"""
        keyboard.append([InlineKeyboardButton(f"🎯 Investir - {project['title']}", callback_data=f"invest_project_{project['id']}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Menu principal", callback_data="main_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

# === SYSTÈME DE DÉPÔT ===

async def deposit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Début du processus de dépôt"""
    await update.callback_query.answer()
    
    message = f"""
💳 **EFFECTUER UN DÉPÔT**

🔹 **Adresse de dépôt USDT (TRC20):**
`TYDzsYUEpvnYmQk4zGP9sWWcTEd2MiAtW6`

📋 **Instructions:**
1. Envoyez vos USDT à l'adresse ci-dessus
2. Montant minimum: 10 USDT
3. Utilisez uniquement le réseau TRC20
4. Conservez le hash de transaction

💰 **Entrez le montant déposé (en USDT):**
    """
    
    await update.callback_query.edit_message_text(message, parse_mode='Markdown')
    return DEPOSIT_AMOUNT

async def deposit_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Récupérer le montant de dépôt"""
    try:
        amount = float(update.message.text)
    except ValueError:
        await update.message.reply_text("❌ Montant invalide. Entrez un nombre.")
        return DEPOSIT_AMOUNT
    
    if amount < 10:
        await update.message.reply_text("❌ Montant minimum: 10 USDT")
        return DEPOSIT_AMOUNT
    
    context.user_data['deposit_amount'] = amount
    
    await update.message.reply_text(
        "✅ Montant enregistré!\n\n"
        "🔗 **Entrez le hash de la transaction:**"
    )
    return DEPOSIT_HASH

async def deposit_hash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Finaliser le dépôt"""
    transaction_hash = update.message.text.strip()
    amount = context.user_data['deposit_amount']
    user = get_user_by_telegram_id(update.effective_user.id)
    
    conn = get_db_connection()
    
    # Créer la transaction en attente
    cursor = conn.execute('''
        INSERT INTO transactions (user_id, type, amount, status, transaction_hash)
        VALUES (?, 'deposit', ?, 'pending', ?)
    ''', (user['id'], amount, transaction_hash))
    
    deposit_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    # Notification admin si disponible
    from telegram_bot import notify_deposit_request
    notify_deposit_request(user['id'], amount, transaction_hash, deposit_id)
    
    add_notification(
        user['id'],
        'Dépôt en cours de vérification',
        f'Votre dépôt de {amount} USDT est en cours de vérification.',
        'info'
    )
    
    context.user_data.clear()
    
    await update.message.reply_text(
        f"""
✅ **DÉPÔT SOUMIS POUR VÉRIFICATION**

💰 **Montant:** {amount:.2f} USDT
🔗 **Hash:** `{transaction_hash}`
🆔 **ID:** #{deposit_id}

⏰ Votre dépôt sera vérifié et crédité sous 24h.

Utilisez /start pour retourner au menu.
        """,
        parse_mode='Markdown'
    )
    
    return ConversationHandler.END

# === SYSTÈME DE RETRAIT ===

async def withdraw_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Début du processus de retrait"""
    await update.callback_query.answer()
    user = get_user_by_telegram_id(update.effective_user.id)
    
    message = f"""
💸 **EFFECTUER UN RETRAIT**

💰 **Solde disponible:** {user['balance']:.2f} USDT
💵 **Montant minimum:** 10 USDT
💸 **Frais de retrait:** 2 USDT

⚠️ **Important:**
- Utilisez uniquement une adresse USDT TRC20
- Vérifiez l'adresse avant confirmation
- Les retraits sont traités sous 24h

💰 **Entrez le montant à retirer:**
    """
    
    await update.callback_query.edit_message_text(message, parse_mode='Markdown')
    return WITHDRAW_AMOUNT

async def withdraw_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Récupérer le montant de retrait"""
    try:
        amount = float(update.message.text)
    except ValueError:
        await update.message.reply_text("❌ Montant invalide. Entrez un nombre.")
        return WITHDRAW_AMOUNT
    
    user = get_user_by_telegram_id(update.effective_user.id)
    
    if amount < 10:
        await update.message.reply_text("❌ Montant minimum: 10 USDT")
        return WITHDRAW_AMOUNT
    
    if amount > user['balance']:
        await update.message.reply_text(f"❌ Solde insuffisant. Disponible: {user['balance']:.2f} USDT")
        return WITHDRAW_AMOUNT
    
    context.user_data['withdraw_amount'] = amount
    net_amount = amount - 2
    
    await update.message.reply_text(
        f"✅ Montant: {amount:.2f} USDT (Net: {net_amount:.2f} USDT)\n\n"
        "📍 **Entrez votre adresse USDT TRC20:**"
    )
    return WITHDRAW_ADDRESS

async def withdraw_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Finaliser le retrait"""
    address = update.message.text.strip()
    amount = context.user_data['withdraw_amount']
    user = get_user_by_telegram_id(update.effective_user.id)
    
    if len(address) < 30:
        await update.message.reply_text("❌ Adresse invalide. Vérifiez et réessayez.")
        return WITHDRAW_ADDRESS
    
    conn = get_db_connection()
    
    # Débiter temporairement le solde
    conn.execute('UPDATE users SET balance = balance - ? WHERE id = ?', (amount, user['id']))
    
    # Créer la transaction en attente
    cursor = conn.execute('''
        INSERT INTO transactions (user_id, type, amount, status, transaction_hash)
        VALUES (?, 'withdrawal', ?, 'pending', ?)
    ''', (user['id'], amount, f"{address}|{amount}"))
    
    withdrawal_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    # Notification admin
    from telegram_bot import notify_withdrawal_request
    notify_withdrawal_request(user['id'], amount, address, withdrawal_id)
    
    add_notification(
        user['id'],
        'Retrait en cours de traitement',
        f'Votre retrait de {amount} USDT est en cours de traitement.',
        'info'
    )
    
    context.user_data.clear()
    
    await update.message.reply_text(
        f"""
✅ **RETRAIT SOUMIS POUR TRAITEMENT**

💰 **Montant:** {amount:.2f} USDT
💵 **Net (après frais):** {amount - 2:.2f} USDT
📍 **Adresse:** `{address}`
🆔 **ID:** #{withdrawal_id}

⏰ Votre retrait sera traité sous 24h.

Utilisez /start pour retourner au menu.
        """,
        parse_mode='Markdown'
    )
    
    return ConversationHandler.END

# === GESTION DES CALLBACKS ===

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestionnaire principal des callbacks"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user = get_user_by_telegram_id(update.effective_user.id)
    
    if data == "main_menu":
        if user:
            await show_main_menu(update, context, user)
        else:
            await query.edit_message_text("❌ Veuillez vous connecter d'abord.")
    
    elif data == "about":
        keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="start")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message = """
🚀 **INVESTCRYPTO PRO**

💎 **La plateforme d'investissement crypto nouvelle génération**

🎯 **Nos avantages:**
• Rendements jusqu'à 15% par jour
• Sécurité blockchain maximale
• Support client 24/7
• Retraits rapides (24h max)
• Interface simple et intuitive

📈 **Types d'investissement:**
• Plans ROI (rendement quotidien)
• Crowdfunding de projets
• Staking de crypto-monnaies
• Plans gelés long terme

🔒 **Sécurité garantie:**
• Fonds sécurisés en cold storage
• Vérifications KYC strictes
• Chiffrement de niveau bancaire
• Audits de sécurité réguliers

💬 **Support:** @InvestCryptoPro_Support
        """
        
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    
    elif data == "wallet":
        await show_wallet(update, context)
    
    elif data == "roi_plans":
        await show_roi_plans(update, context)
    
    elif data == "projects":
        await show_projects(update, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Annuler une conversation"""
    context.user_data.clear()
    await update.message.reply_text(
        "❌ Opération annulée.\n\n"
        "Utilisez /start pour retourner au menu principal."
    )
    return ConversationHandler.END

# === CONFIGURATION ET DÉMARRAGE ===

def setup_user_telegram_bot():
    """Configure le bot utilisateur"""
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN_USER non configuré")
        return None
    
    # Initialiser les colonnes telegram_id si nécessaire
    init_telegram_db()
    
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Handlers de conversation pour l'inscription
    register_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(register_start, pattern="^register$")],
        states={
            REGISTER_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_email)],
            REGISTER_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_password)],
            REGISTER_FIRSTNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_firstname)],
            REGISTER_LASTNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_lastname)],
            REGISTER_REFERRAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_referral)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    # Handlers de conversation pour la connexion
    login_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(login_start, pattern="^login$")],
        states={
            LOGIN_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, login_email)],
            LOGIN_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, login_password)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    # Handlers de conversation pour les dépôts
    deposit_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(deposit_start, pattern="^deposit$")],
        states={
            DEPOSIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_amount)],
            DEPOSIT_HASH: [MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_hash)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    # Handlers de conversation pour les retraits
    withdraw_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(withdraw_start, pattern="^withdraw$")],
        states={
            WITHDRAW_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_amount)],
            WITHDRAW_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_address)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    # Handlers de conversation pour les investissements ROI
    invest_roi_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(invest_roi_start, pattern="^invest_roi_")],
        states={
            INVEST_ROI_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, invest_roi_amount)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    # Ajouter tous les handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(register_handler)
    application.add_handler(login_handler)
    application.add_handler(deposit_handler)
    application.add_handler(withdraw_handler)
    application.add_handler(invest_roi_handler)
    application.add_handler(CallbackQueryHandler(handle_callback))
    
    return application

# Point d'entrée principal
async def start_user_bot():
    """Démarre le bot utilisateur"""
    app = setup_user_telegram_bot()
    if app:
        try:
            await app.initialize()
            await app.start()
            await app.updater.start_polling(
                allowed_updates=["message", "callback_query"],
                drop_pending_updates=True
            )
            print("✅ Bot utilisateur Telegram démarré")
            await app.updater.idle()
        except Exception as e:
            print(f"❌ Erreur bot utilisateur: {e}")
        finally:
            await app.stop()

if __name__ == "__main__":
    asyncio.run(start_user_bot())
