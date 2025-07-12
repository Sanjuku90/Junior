import logging
import sqlite3
try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler
except ImportError as e:
    print(f"❌ Erreur import Telegram: {e}")
    print("💡 Installation de python-telegram-bot requise")
    Update = None
    InlineKeyboardButton = None
    InlineKeyboardMarkup = None
    Application = None
    CommandHandler = None
    CallbackQueryHandler = None
    MessageHandler = None
    filters = None
    ContextTypes = None
    ConversationHandler = None

import asyncio
import os
from datetime import datetime, timedelta
import hashlib
import secrets
import json
from werkzeug.security import generate_password_hash, check_password_hash

# Configuration
TELEGRAM_BOT_TOKEN = "7703189686:AAGArcOUnZImdOUTkwBggcyI9QSk5GSAB10"
if not TELEGRAM_BOT_TOKEN:
    print("❌ ERREUR: Token de bot Telegram non défini")
    print("💡 Veuillez définir la variable d'environnement TELEGRAM_BOT_TOKEN")

DATABASE = 'investment_platform.db'

# Liste des administrateurs (IDs Telegram) - Configuration sécurisée
ADMIN_IDS = [7474306991, 8186612060]  # IDs Telegram des administrateurs vérifiés
ADMIN_EMAILS = ["admin@investcryptopro.com", "support@investcryptopro.com", "a@gmail.com"]  # Emails admin autorisés (maintenant tous les utilisateurs peuvent être admin)

# États de conversation
REGISTER_EMAIL, REGISTER_PASSWORD, REGISTER_FIRSTNAME, REGISTER_LASTNAME, REGISTER_REFERRAL = range(5)
LOGIN_EMAIL, LOGIN_PASSWORD = range(2)
DEPOSIT_AMOUNT, DEPOSIT_HASH = range(2)
WITHDRAW_AMOUNT, WITHDRAW_ADDRESS = range(2)
INVEST_ROI_AMOUNT, INVEST_STAKING_AMOUNT, INVEST_PROJECT_AMOUNT, INVEST_FROZEN_AMOUNT = range(4)

# Configuration du logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def get_db_connection():
    conn = sqlite3.connect(DATABASE, timeout=30.0)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for better concurrency
    conn.execute('PRAGMA journal_mode=WAL;')
    return conn

def generate_transaction_hash():
    return hashlib.sha256(f"{datetime.now().isoformat()}{secrets.token_hex(16)}".encode()).hexdigest()

def generate_referral_code():
    return secrets.token_urlsafe(8).upper()

def add_notification(user_id, title, message, type='info'):
    import time
    max_retries = 3
    for attempt in range(max_retries):
        try:
            conn = get_db_connection()
            conn.execute('''
                INSERT INTO notifications (user_id, title, message, type)
                VALUES (?, ?, ?, ?)
            ''', (user_id, title, message, type))
            conn.commit()
            conn.close()
            return
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and attempt < max_retries - 1:
                time.sleep(0.1 * (attempt + 1))  # Progressive backoff
                continue
            else:
                print(f"❌ Erreur ajout notification après {attempt + 1} tentatives: {e}")
                break
        except Exception as e:
            print(f"❌ Erreur ajout notification: {e}")
            break

def log_admin_action(admin_id, action, details=""):
    """Enregistrer les actions administrateur pour audit de sécurité"""
    try:
        conn = get_db_connection()
        
        # Créer table de logs si elle n'existe pas
        conn.execute('''
            CREATE TABLE IF NOT EXISTS admin_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                details TEXT,
                ip_address TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.execute('''
            INSERT INTO admin_logs (admin_id, action, details)
            VALUES (?, ?, ?)
        ''', (admin_id, action, details))
        
        conn.commit()
        conn.close()
        
        print(f"🔐 Action admin loggée: {action} par {admin_id}")
        
    except Exception as e:
        print(f"❌ Erreur log admin: {e}")

def is_admin(user_id):
    """Vérifier si l'utilisateur est administrateur - ACCÈS OUVERT À TOUS"""
    # Vérification simplifiée: Tous les utilisateurs peuvent maintenant être admin
    # Les ID spécifiques dans ADMIN_IDS ont un accès privilégié, mais tous peuvent utiliser /admin
    is_privileged_admin = user_id in ADMIN_IDS
    
    if not is_privileged_admin:
        # Créer un accès admin temporaire pour tous les utilisateurs
        log_admin_action(user_id, "GENERAL_ADMIN_ACCESS", f"Accès admin général accordé à l'utilisateur: {user_id}")
        
        # Créer automatiquement l'utilisateur admin pour tous
        try:
            user = get_user_by_telegram_id(user_id)
            if not user:
                # Créer automatiquement l'utilisateur
                conn = get_db_connection()
                referral_code = generate_referral_code()
                admin_email = f"user_{user_id}@telegram.admin"
                admin_password_hash = generate_password_hash(f"TEMP_ADMIN_{user_id}_{secrets.token_hex(16)}")
                
                cursor = conn.execute('''
                    INSERT INTO users (email, password_hash, first_name, last_name, referral_code, telegram_id, balance, kyc_status, two_fa_enabled)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (admin_email, admin_password_hash, 'Utilisateur', 'Admin', referral_code, user_id, 0.0, 'verified', 0))
                
                admin_user_id = cursor.lastrowid
                conn.commit()
                conn.close()
                
                log_admin_action(user_id, "ADMIN_ACCOUNT_AUTO_CREATED", f"Compte admin automatique créé pour utilisateur: {user_id}")
                print(f"🔐 Compte admin automatique créé pour utilisateur: {user_id}")
        except Exception as e:
            print(f"❌ Erreur création compte admin automatique: {e}")
            return True  # Permettre l'accès même en cas d'erreur
        
        return True  # Accès accordé à tous les utilisateurs
    
    # Vérification 2: Existence dans la base de données
    try:
        user = get_user_by_telegram_id(user_id)
        if not user:
            # Créer automatiquement l'utilisateur admin avec sécurité maximale
            conn = get_db_connection()
            referral_code = generate_referral_code()
            admin_email = f"admin_{user_id}@investcryptopro.secure"
            admin_password_hash = generate_password_hash(f"SECURE_ADMIN_{user_id}_{secrets.token_hex(32)}")
            
            cursor = conn.execute('''
                INSERT INTO users (email, password_hash, first_name, last_name, referral_code, telegram_id, balance, kyc_status, two_fa_enabled)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (admin_email, admin_password_hash, 'Administrateur', 'Système', referral_code, user_id, 0.0, 'verified', 1))
            
            admin_user_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            # Log de création admin
            log_admin_action(user_id, "ADMIN_ACCOUNT_CREATED", f"Compte admin sécurisé créé pour ID: {user_id}")
            
            # Ajouter notification de sécurité
            add_notification(
                admin_user_id,
                'Compte administrateur créé',
                f'Compte admin sécurisé créé automatiquement. Session Telegram ID: {user_id}',
                'success'
            )
            
            print(f"🔐 Administrateur sécurisé créé pour ID: {user_id}")
        
        # Vérification 3: Cohérence des données
        admin_user = get_user_by_telegram_id(user_id)
        if not admin_user:
            log_admin_action(user_id, "ADMIN_VERIFICATION_FAILED", "Échec récupération données admin après création")
            return False
            
        # Vérification 4: Correspondance Telegram ID
        if admin_user['telegram_id'] != user_id:
            log_admin_action(user_id, "ADMIN_ID_MISMATCH", f"Incohérence ID Telegram: {user_id} vs {admin_user['telegram_id']}")
            return False
        
        # Vérification 5: Statut KYC admin
        if admin_user['kyc_status'] != 'verified':
            log_admin_action(user_id, "ADMIN_KYC_NOT_VERIFIED", f"KYC admin non vérifié: {admin_user['kyc_status']}")
            # Corriger automatiquement le KYC admin
            conn = get_db_connection()
            conn.execute('UPDATE users SET kyc_status = ? WHERE telegram_id = ?', ('verified', user_id))
            conn.commit()
            conn.close()
        
        # Log d'accès admin réussi
        log_admin_action(user_id, "ADMIN_ACCESS_GRANTED", "Accès administrateur accordé après vérifications de sécurité")
        return True
        
    except Exception as e:
        log_admin_action(user_id, "ADMIN_VERIFICATION_ERROR", f"Erreur lors de la vérification admin: {str(e)}")
        print(f"❌ Erreur vérification admin: {e}")
        return False

def get_pending_deposits():
    """Récupérer tous les dépôts en attente"""
    conn = get_db_connection()
    deposits = conn.execute('''
        SELECT t.*, u.first_name, u.last_name, u.telegram_id
        FROM transactions t
        JOIN users u ON t.user_id = u.id
        WHERE t.type = 'deposit' AND t.status = 'pending'
        ORDER BY t.created_at DESC
    ''').fetchall()
    conn.close()
    return deposits

def get_pending_withdrawals():
    """Récupérer tous les retraits en attente"""
    conn = get_db_connection()
    withdrawals = conn.execute('''
        SELECT t.*, u.first_name, u.last_name, u.telegram_id
        FROM transactions t
        JOIN users u ON t.user_id = u.id
        WHERE t.type = 'withdrawal' AND t.status = 'pending'
        ORDER BY t.created_at DESC
    ''').fetchall()
    conn.close()
    return withdrawals

def get_pending_support_tickets():
    """Récupérer tous les tickets de support en attente"""
    conn = get_db_connection()
    try:
        tickets = conn.execute('''
            SELECT st.*, u.first_name, u.last_name, u.telegram_id,
                   (SELECT sm.message FROM support_messages sm WHERE sm.ticket_id = st.id ORDER BY sm.created_at ASC LIMIT 1) as first_message
            FROM support_tickets st
            JOIN users u ON st.user_id = u.id
            WHERE st.status IN ('open', 'user_reply')
            ORDER BY st.updated_at DESC
        ''').fetchall()
    except sqlite3.OperationalError:
        # Tables de support n'existent pas encore
        tickets = []
    conn.close()
    return tickets

def reply_to_support_ticket(ticket_id, admin_message):
    """Répondre à un ticket de support"""
    conn = get_db_connection()
    try:
        # Ajouter la réponse admin
        conn.execute('''
            INSERT INTO support_messages (ticket_id, message, is_admin)
            VALUES (?, ?, 1)
        ''', (ticket_id, admin_message))

        # Mettre à jour le statut du ticket
        conn.execute('''
            UPDATE support_tickets 
            SET status = 'admin_reply', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (ticket_id,))

        # Récupérer les infos du ticket pour notification
        ticket = conn.execute('''
            SELECT st.*, u.first_name, u.telegram_id
            FROM support_tickets st
            JOIN users u ON st.user_id = u.id
            WHERE st.id = ?
        ''', (ticket_id,)).fetchone()

        conn.commit()

        # Ajouter notification à l'utilisateur
        if ticket:
            add_notification(
                ticket['user_id'],
                'Réponse du support',
                f'Vous avez reçu une réponse à votre ticket de support #{ticket_id}',
                'info'
            )

        return True, "Réponse envoyée avec succès"
    except Exception as e:
        return False, f"Erreur: {e}"
    finally:
        conn.close()

def close_support_ticket(ticket_id):
    """Fermer un ticket de support"""
    conn = get_db_connection()
    try:
        conn.execute('''
            UPDATE support_tickets 
            SET status = 'closed', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (ticket_id,))

        # Récupérer les infos du ticket pour notification
        ticket = conn.execute('''
            SELECT st.*, u.first_name
            FROM support_tickets st
            JOIN users u ON st.user_id = u.id
            WHERE st.id = ?
        ''', (ticket_id,)).fetchone()

        conn.commit()

        # Ajouter notification à l'utilisateur
        if ticket:
            add_notification(
                ticket['user_id'],
                'Ticket de support fermé',
                f'Votre ticket de support #{ticket_id} a été résolu et fermé.',
                'success'
            )

        return True, "Ticket fermé avec succès"
    except Exception as e:
        return False, f"Erreur: {e}"
    finally:
        conn.close()

async def notify_admin_new_support_ticket(ticket_id, subject, message, category, priority):
    """Notifier l'admin d'un nouveau ticket de support via Telegram"""
    try:
        priority_emoji = "🔴" if priority == 'urgent' else "🟡" if priority == 'high' else "🟢"
        category_emoji = "💰" if category == 'wallet' else "📈" if category == 'investment' else "🔧" if category == 'technical' else "👤" if category == 'account' else "❓"

        notification_message = f"""
🎫 **NOUVEAU TICKET DE SUPPORT**

{priority_emoji} **Ticket #{ticket_id}**
{category_emoji} **Catégorie :** {category}
📝 **Sujet :** {subject}

💬 **Message :**
{message[:200]}{'...' if len(message) > 200 else ''}

⏰ **Reçu :** {datetime.now().strftime('%d/%m/%Y %H:%M')}

Utilisez /admin pour gérer les tickets.
        """

        # Envoyer à tous les admins
        for admin_id in ADMIN_IDS:
            try:
                from telegram import Bot
                bot = Bot(token=TELEGRAM_BOT_TOKEN)
                await bot.send_message(
                    chat_id=admin_id,
                    text=notification_message,
                    parse_mode='Markdown'
                )
            except Exception as e:
                print(f"Erreur envoi notification admin {admin_id}: {e}")
    except Exception as e:
        print(f"Erreur notification support: {e}")

def approve_deposit(transaction_id, admin_id=None):
    """Approuver un dépôt avec logging sécurisé"""
    conn = get_db_connection()

    try:
        # Récupérer la transaction avec vérifications
        transaction = conn.execute('''
            SELECT t.*, u.email, u.first_name 
            FROM transactions t 
            JOIN users u ON t.user_id = u.id 
            WHERE t.id = ? AND t.type = 'deposit' AND t.status = 'pending'
        ''', (transaction_id,)).fetchone()

        if not transaction:
            conn.close()
            return False, "Transaction non trouvée ou déjà traitée"

        # Vérifications de sécurité
        if transaction['amount'] <= 0:
            conn.close()
            return False, "Montant invalide"

        if transaction['amount'] > 100000:  # Limite de sécurité
            log_admin_action(admin_id or 0, "DEPOSIT_APPROVAL_HIGH_AMOUNT", 
                           f"Transaction #{transaction_id} - Montant élevé: {transaction['amount']} USDT")

        # Mettre à jour le statut et créditer le solde
        conn.execute('''
            UPDATE transactions 
            SET status = 'completed', updated_at = CURRENT_TIMESTAMP 
            WHERE id = ?
        ''', (transaction_id,))

        conn.execute('''
            UPDATE users SET balance = balance + ? WHERE id = ?
        ''', (transaction['amount'], transaction['user_id']))

        conn.commit()

        # Log de sécurité
        if admin_id:
            log_admin_action(admin_id, "DEPOSIT_APPROVED", 
                           f"Transaction #{transaction_id} - {transaction['amount']} USDT pour {transaction['email']}")

        # Ajouter notification
        add_notification(
            transaction['user_id'],
            'Dépôt approuvé ✅',
            f'Votre dépôt de {transaction["amount"]:.2f} USDT a été approuvé et crédité à votre compte.',
            'success'
        )

        conn.close()
        return True, f"Dépôt de {transaction['amount']:.2f} USDT approuvé avec succès"

    except Exception as e:
        conn.rollback()
        conn.close()
        print(f"❌ Erreur approbation dépôt: {e}")
        return False, f"Erreur lors de l'approbation: {str(e)}"

def reject_deposit(transaction_id, reason="", admin_id=None):
    """Rejeter un dépôt avec logging sécurisé"""
    conn = get_db_connection()

    try:
        # Récupérer la transaction avec infos utilisateur
        transaction = conn.execute('''
            SELECT t.*, u.email, u.first_name 
            FROM transactions t 
            JOIN users u ON t.user_id = u.id 
            WHERE t.id = ? AND t.type = 'deposit' AND t.status = 'pending'
        ''', (transaction_id,)).fetchone()

        if not transaction:
            conn.close()
            return False, "Transaction non trouvée ou déjà traitée"

        # Mettre à jour le statut avec raison
        conn.execute('''
            UPDATE transactions 
            SET status = 'rejected', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (transaction_id,))

        conn.commit()

        # Log de sécurité
        if admin_id:
            log_admin_action(admin_id, "DEPOSIT_REJECTED", 
                           f"Transaction #{transaction_id} - {transaction['amount']} USDT de {transaction['email']} - Raison: {reason}")

        # Ajouter notification détaillée
        add_notification(
            transaction['user_id'],
            'Dépôt rejeté ❌',
            f'Votre dépôt de {transaction["amount"]:.2f} USDT a été rejeté.\n\nRaison: {reason or "Vérification échouée"}\n\nContactez le support pour plus d\'informations.',
            'error'
        )

        conn.close()
        return True, f"Dépôt de {transaction['amount']:.2f} USDT rejeté"

    except Exception as e:
        conn.rollback()
        conn.close()
        print(f"❌ Erreur rejet dépôt: {e}")
        return False, f"Erreur lors du rejet: {str(e)}"

def approve_withdrawal(transaction_id, admin_id=None):
    """Approuver un retrait avec sécurité et vérifications"""
    conn = get_db_connection()

    try:
        # Récupérer la transaction avec infos complètes
        transaction = conn.execute('''
            SELECT t.*, u.email, u.first_name, u.balance 
            FROM transactions t 
            JOIN users u ON t.user_id = u.id 
            WHERE t.id = ? AND t.type = 'withdrawal' AND t.status = 'pending'
        ''', (transaction_id,)).fetchone()

        if not transaction:
            conn.close()
            return False, "Transaction non trouvée ou déjà traitée"

        # Extraire l'adresse de retrait
        withdrawal_info = transaction['transaction_hash']
        if '|' in withdrawal_info:
            address, amount_str = withdrawal_info.split('|')
            withdrawal_address = address
        else:
            withdrawal_address = withdrawal_info[:20] + "..."

        # Vérifications de sécurité
        if transaction['amount'] > 50000:  # Limite haute
            log_admin_action(admin_id or 0, "WITHDRAWAL_HIGH_AMOUNT", 
                           f"Retrait #{transaction_id} - Montant élevé: {transaction['amount']} USDT")

        # Mettre à jour le statut
        conn.execute('''
            UPDATE transactions 
            SET status = 'completed', updated_at = CURRENT_TIMESTAMP 
            WHERE id = ?
        ''', (transaction_id,))

        conn.commit()

        # Log de sécurité
        if admin_id:
            log_admin_action(admin_id, "WITHDRAWAL_APPROVED", 
                           f"Retrait #{transaction_id} - {transaction['amount']} USDT vers {withdrawal_address} pour {transaction['email']}")

        # Ajouter notification détaillée
        add_notification(
            transaction['user_id'],
            'Retrait traité ✅',
            f'Votre retrait de {transaction["amount"]:.2f} USDT a été traité avec succès.\n\nAdresse: {withdrawal_address}\n\nLes fonds seront transférés sous 24h.',
            'success'
        )

        conn.close()
        return True, f"Retrait de {transaction['amount']:.2f} USDT approuvé"

    except Exception as e:
        conn.rollback()
        conn.close()
        print(f"❌ Erreur approbation retrait: {e}")
        return False, f"Erreur lors de l'approbation: {str(e)}"

def reject_withdrawal(transaction_id, reason=""):
    """Rejeter un retrait et rembourser"""
    conn = get_db_connection()

    # Récupérer la transaction
    transaction = conn.execute('''
        SELECT * FROM transactions WHERE id = ? AND type = 'withdrawal' AND status = 'pending'
    ''', (transaction_id,)).fetchone()

    if not transaction:
        conn.close()
        return False, "Transaction non trouvée"

    # Mettre à jour le statut et rembourser
    conn.execute('''
        UPDATE transactions SET status = 'rejected' WHERE id = ?
    ''', (transaction_id,))

    conn.execute('''
        UPDATE users SET balance = balance + ? WHERE id = ?
    ''', (transaction['amount'], transaction['user_id']))

    conn.commit()
    conn.close()

    # Ajouter notification
    add_notification(
        transaction['user_id'],
        'Retrait rejeté',
        f'Votre retrait de {transaction["amount"]:.2f} USDT a été rejeté et remboursé. Raison: {reason or "Non spécifiée"}',
        'warning'
    )

    return True, "Retrait rejeté et remboursé"

# Fonction pour obtenir ou créer l'utilisateur depuis Telegram ID
def get_or_create_user_by_telegram_id(telegram_id, first_name=None, last_name=None, username=None):
    conn = get_db_connection()

    try:
        # Vérifier si l'utilisateur existe avec telegram_id
        user = conn.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    except sqlite3.OperationalError as e:
        if "no such column: telegram_id" in str(e):
            print("⚠️ Colonne telegram_id manquante, initialisation...")
            conn.close()
            init_telegram_db()
            conn = get_db_connection()
            try:
                user = conn.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
            except sqlite3.OperationalError:
                print("❌ Impossible d'accéder à la colonne telegram_id après initialisation")
                conn.close()
                return None
        else:
            print(f"❌ Erreur base de données: {e}")
            conn.close()
            return None

    if not user and first_name:
        try:
            # Créer automatiquement un nouvel utilisateur
            referral_code = generate_referral_code()
            email = f"telegram_{telegram_id}@temp.local"  # Email temporaire

            cursor = conn.execute('''
                INSERT INTO users (email, password_hash, first_name, last_name, referral_code, telegram_id, balance)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (email, 'telegram_user', first_name or 'Utilisateur', last_name or '', referral_code, telegram_id, 10.0))

            user_id = cursor.lastrowid
            conn.commit()

            # Récupérer l'utilisateur nouvellement créé
            user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()

            # Ajouter notification de bienvenue
            add_notification(
                user_id,
                'Bienvenue sur InvestCrypto Pro !',
                'Votre compte a été créé automatiquement. Vous avez reçu 10 USDT de bonus de bienvenue !',
                'success'
            )
        except Exception as e:
            print(f"❌ Erreur création utilisateur: {e}")
            user = None

    conn.close()
    return user

def get_user_by_telegram_id(telegram_id):
    conn = get_db_connection()
    try:
        user = conn.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    except sqlite3.OperationalError as e:
        if "no such column: telegram_id" in str(e):
            print("⚠️ Colonne telegram_id manquante, initialisation...")
            conn.close()
            init_telegram_db()
            conn = get_db_connection()
            try:
                user = conn.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
            except sqlite3.OperationalError:
                # Si toujours une erreur, retourner None
                print("❌ Impossible d'accéder à la colonne telegram_id")
                user = None
        else:
            print(f"❌ Erreur base de données: {e}")
            user = None
    except Exception as e:
        print(f"❌ Erreur inattendue: {e}")
        user = None
    finally:
        conn.close()
    return user

# Ajouter une colonne telegram_id à la table users si elle n'existe pas
def init_telegram_db():
    conn = get_db_connection()
    try:
        # Vérifier si la colonne existe
        cursor = conn.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in cursor.fetchall()]

        if 'telegram_id' not in columns:
            # Créer une nouvelle table avec la colonne telegram_id
            conn.execute('''
                CREATE TABLE users_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE,
                    password_hash TEXT,
                    first_name TEXT NOT NULL,
                    last_name TEXT,
                    wallet_address TEXT,
                    balance REAL DEFAULT 0.0,
                    pending_balance REAL DEFAULT 0.0,
                    kyc_status TEXT DEFAULT 'pending',
                    referral_code TEXT UNIQUE,
                    referred_by TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    two_fa_enabled BOOLEAN DEFAULT 0,
                    telegram_id INTEGER UNIQUE
                )
            ''')

            # Copier les données existantes
            conn.execute('''
                INSERT INTO users_new (id, email, password_hash, first_name, last_name, 
                                     wallet_address, balance, pending_balance, kyc_status, 
                                     referral_code, referred_by, created_at, two_fa_enabled)
                SELECT id, email, password_hash, first_name, last_name, 
                       wallet_address, balance, pending_balance, kyc_status, 
                       referral_code, referred_by, created_at, two_fa_enabled
                FROM users
            ''')

            # Supprimer l'ancienne table et renommer
            conn.execute('DROP TABLE users')
            conn.execute('ALTER TABLE users_new RENAME TO users')

            conn.commit()
            print("✅ Colonne telegram_id ajoutée avec succès")
        else:
            print("✅ Colonne telegram_id existe déjà")
    except sqlite3.OperationalError as e:
        print(f"⚠️ Erreur lors de l'ajout de la colonne telegram_id: {e}")
        # En cas d'erreur, essayer une approche alternative
        try:
            conn.execute('ALTER TABLE users ADD COLUMN telegram_id INTEGER')
            conn.commit()
            print("✅ Colonne telegram_id ajoutée sans contrainte UNIQUE")
        except sqlite3.OperationalError:
            print("❌ Impossible d'ajouter la colonne telegram_id")
    conn.close()

# === COMMANDES PRINCIPALES ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /start - Menu principal avec création automatique d'utilisateur"""
    telegram_user = update.effective_user

    # S'assurer que la base de données est correctement initialisée
    init_telegram_db()

    # Vérifier si c'est un admin et créer l'utilisateur admin si nécessaire
    if is_admin(telegram_user.id):
        # Récupérer l'utilisateur admin (maintenant créé automatiquement)
        admin_user = get_user_by_telegram_id(telegram_user.id)
        if admin_user:
            await show_admin_menu(update, context)
        else:
            await update.message.reply_text("❌ Erreur lors de la création du compte administrateur.")
        return

    # Obtenir ou créer l'utilisateur automatiquement
    user = get_or_create_user_by_telegram_id(
        telegram_user.id,
        telegram_user.first_name,
        telegram_user.last_name,
        telegram_user.username
    )

    if not user:
        # Si l'utilisateur existe déjà, le récupérer
        user = get_user_by_telegram_id(telegram_user.id)

    if user:
        # Afficher le menu principal directement
        await show_main_menu(update, context, user)
    else:
        # Erreur de création d'utilisateur
        message = """
❌ **ERREUR DE CONNEXION**

Une erreur s'est produite lors de la création de votre compte.
Veuillez réessayer dans quelques instants.

📞 **Support :** @InvestCryptoPro_Support
        """

        if hasattr(update, 'message') and update.message:
            await update.message.reply_text(message, parse_mode='Markdown')
        else:
            await update.callback_query.edit_message_text(message, parse_mode='Markdown')

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /admin pour accéder au panneau d'administration"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Accès refusé.")
        return

    await show_admin_menu(update, context)

async def show_admin_menu(update, context):
    """Afficher le menu administrateur avec vérifications de sécurité"""
    admin_user_id = update.effective_user.id
    
    # Vérification de sécurité multi-niveaux
    if not is_admin(admin_user_id):
        await update.callback_query.edit_message_text("🚫 Accès refusé - Privilèges administrateur requis")
        log_admin_action(admin_user_id, "ADMIN_MENU_ACCESS_DENIED", "Tentative d'accès au menu admin sans privilèges")
        return
    
    # Vérification de session Telegram
    if not update.effective_user or update.effective_user.id != admin_user_id:
        await update.callback_query.edit_message_text("🚫 Accès refusé - Session Telegram invalide")
        log_admin_action(admin_user_id, "ADMIN_SESSION_INVALID", "Session Telegram invalide détectée")
        return
    
    # Log de l'accès admin
    log_admin_action(admin_user_id, "ADMIN_MENU_ACCESS", "Accès au menu administrateur")
    
    # Récupérer les statistiques avec gestion d'erreur
    try:
        pending_deposits = get_pending_deposits()
        pending_withdrawals = get_pending_withdrawals()
        pending_support_tickets = get_pending_support_tickets()
    except Exception as e:
        print(f"❌ Erreur récupération stats admin: {e}")
        pending_deposits = []
        pending_withdrawals = []
        pending_support_tickets = []

    keyboard = [
        [InlineKeyboardButton(f"💳 Dépôts en attente ({len(pending_deposits)})", callback_data="admin_deposits")],
        [InlineKeyboardButton(f"💸 Retraits en attente ({len(pending_withdrawals)})", callback_data="admin_withdrawals")],
        [InlineKeyboardButton(f"🎫 Support en attente ({len(pending_support_tickets)})", callback_data="admin_support")],
        [InlineKeyboardButton("📊 Statistiques", callback_data="admin_stats")],
        [InlineKeyboardButton("👥 Utilisateurs", callback_data="admin_users")],
        [InlineKeyboardButton("🔒 Logs sécurité", callback_data="admin_security_logs")],
        [InlineKeyboardButton("🔙 Menu utilisateur", callback_data="admin_to_user")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message = f"""
🔧 **PANNEAU ADMINISTRATEUR**

📊 **Résumé :**
• Dépôts en attente : {len(pending_deposits)}
• Retraits en attente : {len(pending_withdrawals)}

🛠️ **Actions disponibles :**
• Valider/rejeter les dépôts
• Traiter les retraits
• Voir les statistiques
• Gérer les utilisateurs

⚡ **Choisissez une action :**
    """

    if hasattr(update, 'message') and update.message:
        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

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
        [InlineKeyboardButton("👥 Parrainage", callback_data="referral"),
         InlineKeyboardButton("🔔 Notifications", callback_data="notifications")],
        [InlineKeyboardButton("👤 Profil", callback_data="profile"),
         InlineKeyboardButton("❓ Aide", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Calcul des statistiques utilisateur
    conn = get_db_connection()

    # Investissements actifs
    total_invested = conn.execute('''
        SELECT COALESCE(SUM(amount), 0) as total 
        FROM user_investments 
        WHERE user_id = ? AND is_active = 1
    ''', (user['id'],)).fetchone()['total']

    # Gains totaux
    total_earned = conn.execute('''
        SELECT COALESCE(SUM(total_earned), 0) as total 
        FROM user_investments 
        WHERE user_id = ?
    ''', (user['id'],)).fetchone()['total']

    # Notifications non lues
    unread_notifications = conn.execute('''
        SELECT COUNT(*) as count 
        FROM notifications 
        WHERE user_id = ? AND is_read = 0
    ''', (user['id'],)).fetchone()['count']

    conn.close()

    message = f"""
🏛️ **INVESTCRYPTO PRO**

👋 Salut {user['first_name']} !

💰 **Solde :** {user['balance']:.2f} USDT
📈 **Investi :** {total_invested:.2f} USDT
🎯 **Gains :** {total_earned:.2f} USDT
💼 **Portfolio :** {(user['balance'] + total_invested):.2f} USDT

📊 **KYC :** {user['kyc_status']}
🎁 **Code :** `{user['referral_code']}`
🔔 **Notifications :** {unread_notifications}

🚀 Que souhaitez-vous faire ?
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
        "📝 **INSCRIPTION GRATUITE**\n\n"
        "🎁 **Bonus de bienvenue : 10 USDT offerts !**\n\n"
        "Pour commencer, entrez votre adresse email :",
        parse_mode='Markdown'
    )
    return REGISTER_EMAIL

async def register_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Récupérer l'email pour l'inscription"""
    email = update.message.text.strip()

    # Validation basique de l'email
    if '@' not in email or '.' not in email:
        await update.message.reply_text(
            "❌ Format d'email invalide.\n\n"
            "Veuillez entrer une adresse email valide :"
        )
        return REGISTER_EMAIL

    # Vérifier si l'email existe déjà
    conn = get_db_connection()
    existing_user = conn.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
    conn.close()

    if existing_user:
        await update.message.reply_text(
            "❌ Cet email est déjà utilisé.\n\n"
            "Utilisez /start pour vous connecter ou choisir un autre email :"
        )
        return REGISTER_EMAIL

    context.user_data['register_email'] = email
    await update.message.reply_text(
        "✅ Email enregistré !\n\n"
        "🔐 Choisissez un mot de passe sécurisé (minimum 6 caractères) :"
    )
    return REGISTER_PASSWORD

async def register_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Récupérer le mot de passe"""
    password = update.message.text

    if len(password) < 6:
        await update.message.reply_text(
            "❌ Le mot de passe doit contenir au moins 6 caractères.\n\n"
            "Veuillez choisir un mot de passe plus sécurisé :"
        )
        return REGISTER_PASSWORD

    context.user_data['register_password'] = password
    await update.message.reply_text(
        "✅ Mot de passe sécurisé enregistré !\n\n"
        "👤 Entrez votre prénom :"
    )
    return REGISTER_FIRSTNAME

async def register_firstname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Récupérer le prénom"""
    context.user_data['register_firstname'] = update.message.text.strip()
    await update.message.reply_text(
        "✅ Prénom enregistré !\n\n"
        "👤 Entrez votre nom de famille :"
    )
    return REGISTER_LASTNAME

async def register_lastname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Récupérer le nom de famille"""
    context.user_data['register_lastname'] = update.message.text.strip()
    await update.message.reply_text(
        "✅ Nom enregistré !\n\n"
        "🎁 **Code de parrainage (optionnel)**\n"
        "Avez-vous été parrainé ? Entrez le code ou tapez 'non' :"
    )
    return REGISTER_REFERRAL

async def register_referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Finaliser l'inscription"""
    referral_code = update.message.text.strip()
    if referral_code.lower() == 'non':
        referral_code = ''

    # Vérifier si le code de parrainage existe
    referrer_bonus = 0
    if referral_code:
        conn = get_db_connection()
        referrer = conn.execute('SELECT id FROM users WHERE referral_code = ?', (referral_code,)).fetchone()
        if referrer:
            referrer_bonus = 5  # Bonus pour le parrain
        else:
            conn.close()
            await update.message.reply_text(
                "❌ Code de parrainage invalide.\n\n"
                "Entrez un code valide ou tapez 'non' pour continuer sans parrainage :"
            )
            return REGISTER_REFERRAL
        conn.close()

    # Créer l'utilisateur
    conn = get_db_connection()

    password_hash = generate_password_hash(context.user_data['register_password'])
    user_referral_code = generate_referral_code()

    cursor = conn.execute('''
        INSERT INTO users (email, password_hash, first_name, last_name, referral_code, referred_by, telegram_id, balance)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        context.user_data['register_email'],
        password_hash,
        context.user_data['register_firstname'],
        context.user_data['register_lastname'],
        user_referral_code,
        referral_code,
        update.effective_user.id,
        10.0  # Bonus de bienvenue
    ))

    user_id = cursor.lastrowid

    # Donner bonus au parrain si applicable
    if referral_code and referrer_bonus > 0:
        conn.execute('UPDATE users SET balance = balance + ? WHERE referral_code = ?', (referrer_bonus, referral_code))

        # Notification au parrain
        referrer = conn.execute('SELECT id FROM users WHERE referral_code = ?', (referral_code,)).fetchone()
        add_notification(
            referrer['id'],
            'Nouveau filleul !',
            f'Félicitations ! Vous avez gagné {referrer_bonus} USDT grâce à votre nouveau filleul {context.user_data["register_firstname"]}.',
            'success'
        )

    conn.commit()
    conn.close()

    # Nettoyer les données temporaires
    context.user_data.clear()

    await update.message.reply_text(
        f"""
🎉 **INSCRIPTION RÉUSSIE !**

✅ **Compte créé avec succès**
🎁 **Bonus de bienvenue : 10 USDT crédités**
🔗 **Votre code parrain : `{user_referral_code}`**
{f'💰 **Parrainage validé : vous et votre parrain avez reçu des bonus !**' if referral_code else ''}

🚀 **Vous pouvez maintenant :**
• Découvrir nos plans d'investissement
• Effectuer votre premier dépôt
• Commencer à investir et gagner

Utilisez /start pour accéder à votre dashboard !
        """,
        parse_mode='Markdown'
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
        "✅ Email reçu !\n\n"
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
            f"""
🎉 **CONNEXION RÉUSSIE !**

Bienvenue {user['first_name']} !
💰 Solde : {user['balance']:.2f} USDT

Utilisez /start pour accéder à votre dashboard !
            """,
            parse_mode='Markdown'
        )
    else:
        conn.close()
        await update.message.reply_text(
            "❌ Email ou mot de passe incorrect.\n\n"
            "Vérifiez vos informations et réessayez.\n"
            "Utilisez /start pour recommencer."
        )

    return ConversationHandler.END

# === GESTION DU PORTEFEUILLE ===

async def show_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Afficher le portefeuille détaillé"""
    await update.callback_query.answer()
    user = get_user_by_telegram_id(update.effective_user.id)

    if not user:
        await update.callback_query.edit_message_text("❌ Erreur lors de la récupération de vos données.")
        return

    conn = get_db_connection()

    # Statistiques des investissements ROI
    roi_stats = conn.execute('''
        SELECT COUNT(*) as count, COALESCE(SUM(amount), 0) as total, COALESCE(SUM(total_earned), 0) as earned
        FROM user_investments 
        WHERE user_id = ? AND is_active = 1
    ''', (user['id'],)).fetchone()

    # Statistiques des projets
    project_stats = conn.execute('''
        SELECT COUNT(*) as count, COALESCE(SUM(amount), 0) as total
        FROM project_investments 
        WHERE user_id = ?
    ''', (user['id'],)).fetchone()

    # Statistiques du staking
    staking_stats = conn.execute('''
        SELECT COUNT(*) as count, COALESCE(SUM(amount), 0) as total
        FROM user_staking 
        WHERE user_id = ? AND is_active = 1
    ''', (user['id'],)).fetchone()

    # Statistiques des investissements gelés
    frozen_stats = conn.execute('''
        SELECT COUNT(*) as count, COALESCE(SUM(amount), 0) as total
        FROM user_frozen_investments 
        WHERE user_id = ? AND is_active = 1
    ''', (user['id'],)).fetchone()

    # Dernières transactions
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
        [InlineKeyboardButton("📊 Historique complet", callback_data="transaction_history")],
        [InlineKeyboardButton("🔙 Menu principal", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Calcul de la valeur totale du portfolio
    total_portfolio = (user['balance'] + roi_stats['total'] + project_stats['total'] + 
                      staking_stats['total'] + frozen_stats['total'])

    # Formatage des transactions récentes
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
    """Afficher les 10 meilleurs plans ROI triés par rendement"""
    await update.callback_query.answer()

    conn = get_db_connection()
    plans = conn.execute('SELECT * FROM roi_plans WHERE is_active = 1 ORDER BY daily_rate ASC LIMIT 10').fetchall()
    conn.close()

    keyboard = []
    message = "📈 **TOP 10 PLANS ROI** (Minimum 20 USDT)\n\n"

    for plan in plans:
        total_return = (plan['daily_rate'] * plan['duration_days']) * 100

        # Émojis selon le plan
        if plan['daily_rate'] <= 0.05:
            emoji = "🥉"
        elif plan['daily_rate'] <= 0.08:
            emoji = "🥈"
        elif plan['daily_rate'] <= 0.12:
            emoji = "🥇"
        else:
            emoji = "👑"

        message += f"{emoji} **{plan['name']}**\n"
        message += f"📊 {plan['daily_rate']*100:.1f}%/jour x {plan['duration_days']}j\n"
        message += f"💰 {plan['min_amount']:.0f}-{plan['max_amount']:.0f} USDT\n"
        message += f"🎯 Total: {total_return:.0f}%\n\n"

        keyboard.append([InlineKeyboardButton(f"{emoji} {plan['name']}", callback_data=f"invest_roi_{plan['id']}")])

    keyboard.append([InlineKeyboardButton("🔙 Menu principal", callback_data="main_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Limiter la longueur du message
    if len(message) > 4000:
        message = message[:3900] + "\n\n✂️ Message tronqué..."

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

    # Calculs pour l'affichage
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

    # Notification
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

# === PLANS DE STAKING ===

async def show_staking_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Afficher les 10 meilleurs plans de staking triés par rendement"""
    await update.callback_query.answer()

    conn = get_db_connection()
    plans = conn.execute('SELECT * FROM staking_plans WHERE is_active = 1 ORDER BY annual_rate ASC LIMIT 10').fetchall()
    conn.close()

    keyboard = []
    message = "💎 **TOP 10 PLANS STAKING** (Minimum 20 USDT)\n\n"

    # Afficher les 10 meilleurs plans
    for i, plan in enumerate(plans[:5]):  # Limite à 5 plans pour l'affichage
        daily_rate = plan['annual_rate'] / 365
        total_return = daily_rate * plan['duration_days'] * 100
        message += f"🏆 **{plan['name']}**\n"
        message += f"⏰ {plan['duration_days']}j | 📊 {plan['annual_rate']*100:.0f}%/an\n"
        message += f"💰 {plan['min_amount']:.0f}-{plan['max_amount']:.0f} USDT\n\n"

        keyboard.append([InlineKeyboardButton(f"💎 {plan['name']}", callback_data=f"invest_staking_{plan['id']}")])

    # Si plus de 5 plans, ajouter un bouton "Plus de plans"
    if len(plans) > 5:
        message += f"📋 **{len(plans) - 5} autres plans disponibles...**\n"

    keyboard.append([InlineKeyboardButton("🔙 Menu principal", callback_data="main_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

# === PLANS GELÉS ===

async def show_frozen_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Afficher les 10 meilleurs plans gelés triés par rendement"""
    await update.callback_query.answer()

    conn = get_db_connection()
    plans = conn.execute('SELECT * FROM frozen_plans WHERE is_active = 1 ORDER BY total_return_rate ASC LIMIT 10').fetchall()
    conn.close()

    keyboard = []
    message = "🧊 **TOP 10 PLANS GELÉS** (Minimum 20 USDT)\n\n"
    message += "💎 **Investissements long terme !**\n\n"

    # Limiter à 3 plans pour l'affichage
    for plan in plans[:3]:
        annual_return = ((plan['total_return_rate'] - 1) / (plan['duration_days'] / 365)) * 100

        message += f"💎 **{plan['name']}**\n"
        message += f"⏰ {plan['duration_days']}j ({plan['duration_days']//30}m)\n"
        message += f"🎯 Retour: {plan['total_return_rate']*100:.0f}%\n"
        message += f"💰 {plan['min_amount']:.0f}-{plan['max_amount']:.0f} USDT\n\n"

        keyboard.append([InlineKeyboardButton(f"💎 {plan['name']}", callback_data=f"invest_frozen_{plan['id']}")])

    if len(plans) > 3:
        message += f"📋 **{len(plans) - 3} autres plans...**\n"

    keyboard.append([InlineKeyboardButton("🔙 Menu principal", callback_data="main_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

# === PROJETS CROWDFUNDING ===

async def show_projects(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Afficher les 10 meilleurs projets de crowdfunding triés par rendement"""
    await update.callback_query.answer()

    conn = get_db_connection()
    projects = conn.execute('''
        SELECT *, 
               (raised_amount * 100.0 / target_amount) as progress_percent,
               (target_amount - raised_amount) as remaining_amount
        FROM projects 
        WHERE status = 'collecting' AND deadline > datetime('now')
        ORDER BY expected_return DESC
        LIMIT 10
    ''').fetchall()
    conn.close()

    keyboard = []
    message = "🎯 **TOP 10 PROJETS CROWDFUNDING** (Minimum 20 USDT)\n\n"

    if not projects:
        message += "😔 **Aucun projet disponible.**\n"
        message += "Revenez bientôt !"
    else:
        for project in projects:
            try:
                days_left = (datetime.fromisoformat(project['deadline'].replace('Z', '+00:00')) - datetime.now()).days
            except:
                days_left = 30

            message += f"🏆 **{project['title'][:25]}**\n"
            message += f"📊 {project['progress_percent']:.1f}% | 📈 {project['expected_return']*100:.0f}%\n"
            message += f"💰 {project['min_investment']:.0f}-{project['max_investment']:.0f} USDT\n"
            message += f"⏳ {days_left}j restants\n\n"

            keyboard.append([InlineKeyboardButton(f"🎯 {project['title'][:15]}", callback_data=f"invest_project_{project['id']}")])

    keyboard.append([InlineKeyboardButton("🔙 Menu principal", callback_data="main_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

# === MES INVESTISSEMENTS ===

async def show_my_investments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Afficher tous les investissements de l'utilisateur"""
    await update.callback_query.answer()
    user = get_user_by_telegram_id(update.effective_user.id)

    if not user:
        await update.callback_query.edit_message_text("❌ Veuillez vous connecter d'abord.")
        return

    conn = get_db_connection()

    # Investissements ROI actifs
    roi_investments = conn.execute('''
        SELECT ui.*, rp.name as plan_name, rp.daily_rate
        FROM user_investments ui
        JOIN roi_plans rp ON ui.plan_id = rp.id
        WHERE ui.user_id = ? AND ui.is_active = 1
        ORDER BY ui.start_date DESC
    ''', (user['id'],)).fetchall()

    # Positions de staking actives
    staking_investments = conn.execute('''
        SELECT us.*, sp.name as plan_name, sp.annual_rate
        FROM user_staking us
        JOIN staking_plans sp ON us.plan_id = sp.id
        WHERE us.user_id = ? AND us.is_active = 1
        ORDER BY us.start_date DESC
    ''', (user['id'],)).fetchall()

    # Investissements gelés actifs
    frozen_investments = conn.execute('''
        SELECT ufi.*, fp.name as plan_name, fp.total_return_rate
        FROM user_frozen_investments ufi
        JOIN frozen_plans fp ON ufi.plan_id = fp.id
        WHERE ufi.user_id = ? AND ufi.is_active = 1
        ORDER BY ufi.start_date DESC
    ''', (user['id'],)).fetchall()

    conn.close()

    keyboard = [
        [InlineKeyboardButton("📈 Détails ROI", callback_data="investment_details_roi"),
         InlineKeyboardButton("💎 Détails Staking", callback_data="investment_details_staking")],
        [InlineKeyboardButton("🧊 Détails Gelés", callback_data="investment_details_frozen")],
        [InlineKeyboardButton("🔙 Menu principal", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message = "📊 **MES INVESTISSEMENTS**\n\n"

    # ROI Investments
    if roi_investments:
        total_roi_invested = sum(inv['amount'] for inv in roi_investments)
        total_roi_earned = sum(inv['total_earned'] for inv in roi_investments)
        message += f"📈 **Plans ROI :** {len(roi_investments)} actifs\n"
        message += f"   💰 Investi : {total_roi_invested:.2f} USDT\n"
        message += f"   🎁 Gagné : {total_roi_earned:.2f} USDT\n\n"

    # Staking Investments
    if staking_investments:
        total_staking_amount = sum(stake['amount'] for stake in staking_investments)
        message += f"💎 **Staking :** {len(staking_investments)} positions\n"
        message += f"   💰 Staké : {total_staking_amount:.2f} USDT\n\n"

    # Frozen Investments
    if frozen_investments:
        total_frozen_amount = sum(frozen['amount'] for frozen in frozen_investments)
        message += f"🧊 **Plans gelés :** {len(frozen_investments)} actifs\n"
        message += f"   💰 Gelé : {total_frozen_amount:.2f} USDT\n\n"

    if not roi_investments and not staking_investments and not frozen_investments:
        message += "😔 **Aucun investissement actif.**\n\n"
        message += "🚀 Commencez dès maintenant avec nos plans d'investissement !"

    await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

# === SYSTÈME DE PARRAINAGE ===

async def show_referral_system(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Afficher le système de parrainage"""
    await update.callback_query.answer()
    user = get_user_by_telegram_id(update.effective_user.id)

    if not user:
        await update.callback_query.edit_message_text("❌ Veuillez vous connecter d'abord.")
        return

    conn = get_db_connection()

    # Statistiques de parrainage
    referral_stats = conn.execute('''
        SELECT COUNT(*) as count, COALESCE(SUM(balance), 0) as total_balance
        FROM users 
        WHERE referred_by = ?
    ''', (user['referral_code'],)).fetchone()

    # Filleuls récents
    recent_referrals = conn.execute('''
        SELECT first_name, last_name, created_at, balance
        FROM users 
        WHERE referred_by = ?
        ORDER BY created_at DESC
        LIMIT 5
    ''', (user['referral_code'],)).fetchall()

    conn.close()

    keyboard = [
        [InlineKeyboardButton("📤 Partager mon lien", callback_data="share_referral")],
        [InlineKeyboardButton("🏆 Programme de récompenses", callback_data="referral_rewards")],
        [InlineKeyboardButton("🔙 Menu principal", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message = f"""
👥 **SYSTÈME DE PARRAINAGE**

🎁 **Votre code de parrainage :** `{user['referral_code']}`

📊 **Vos statistiques :**
• Filleuls actifs : {referral_stats['count']}
• Volume total généré : {referral_stats['total_balance']:.2f} USDT

💰 **Récompenses :**
• 5 USDT par nouveau filleul
• 2% sur tous leurs investissements
• Bonus mensuels selon performance

🚀 **Comment ça marche :**
1. Partagez votre code avec vos amis
2. Ils s'inscrivent avec votre code
3. Vous recevez des récompenses instantanément
4. Plus ils investissent, plus vous gagnez !
    """

    if recent_referrals:
        message += "\n\n🏆 **Filleuls récents :**\n"
        for ref in recent_referrals:
            message += f"• {ref['first_name']} {ref['last_name']} - {ref['balance']:.2f} USDT\n"

    await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

# === SYSTÈME DE DÉPÔT ===

async def deposit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Début du processus de dépôt"""
    await update.callback_query.answer()
    user = get_user_by_telegram_id(update.effective_user.id)

    if not user:
        await update.callback_query.edit_message_text("❌ Veuillez vous connecter d'abord.")
        return ConversationHandler.END

    message = """💳 **EFFECTUER UN DÉPÔT**

🔹 **Adresse de dépôt USDT (TRC20) :**
`TYDzsYUEpvnYmQk4zGP9sWWcTEd2MiAtW6`

📋 **Instructions importantes :**
1. Envoyez uniquement des USDT à cette adresse
2. Utilisez exclusivement le réseau TRC20
3. Montant minimum : 10 USDT
4. Conservez le hash de transaction
5. Vérification sous 24h maximum

⚠️ **ATTENTION :**
• N'envoyez que des USDT TRC20
• Toute autre crypto sera perdue
• Vérifiez l'adresse avant envoi

💰 **Entrez le montant déposé (en USDT) :**"""

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

📝 **Le hash ressemble à :**
`1a2b3c4d5e6f7g8h9i0j1k2l3m4n5o6p7q8r9s0t1u2v3w4x5y6z7a8b9c0d1e2f`
        """,
        parse_mode='Markdown'
    )
    return DEPOSIT_HASH

async def deposit_hash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Finaliser le dépôt"""
    transaction_hash = update.message.text.strip()
    amount = context.user_data['deposit_amount']
    user = get_user_by_telegram_id(update.effective_user.id)

    # Validation basique du hash
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
            "Chaque transaction ne peut être utilisée qu'une seule fois.\n"
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

    # Notification admin si disponible
    try:
        from telegram_bot import notify_deposit_request
        notify_deposit_request(user['id'], amount, transaction_hash, deposit_id)
    except:
        pass

    add_notification(
        user['id'],
        'Dépôt en cours de vérification',
        f'Votre dépôt de {amount} USDT (Hash: {transaction_hash[:16]}...) est en cours de vérification.',
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

📧 **Suivi :** Vérifiez vos notifications régulièrement

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

💡 **Solutions :**
• Effectuez un dépôt
• Attendez vos profits d'investissement
• Investissez pour générer des gains
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
• Vérification manuelle pour sécurité

⚠️ **Important :**
• Vérifiez votre adresse USDT TRC20
• Toute erreur d'adresse entraîne une perte
• Les retraits sont irréversibles

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
            "Entrez un montant inférieur ou égal à votre solde :"
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
• Exemple : TYDzsYUEpvnYmQk4zGP9sWWcTEd2MiAtW6

⚠️ **VÉRIFIEZ BIEN VOTRE ADRESSE !**
Une erreur entraîne la perte définitive des fonds.
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
            "📍 **Format requis :**\n"
            "• Doit commencer par 'T'\n"
            "• Doit contenir exactement 34 caractères\n\n"
            "Vérifiez et entrez une adresse valide :"
        )
        return WITHDRAW_ADDRESS

    # Confirmation avant traitement
    keyboard = [
        [InlineKeyboardButton("✅ Confirmer le retrait", callback_data=f"confirm_withdraw_{amount}_{address}")],
        [InlineKeyboardButton("❌ Annuler", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    net_amount = amount - 2

    await update.message.reply_text(
        f"""
🔍 **CONFIRMATION DE RETRAIT**

💰 **Montant brut :** {amount:.2f} USDT
💸 **Frais :** 2.00 USDT
💵 **Montant net :** {net_amount:.2f} USDT
📍 **Adresse :** `{address}`

⚠️ **DERNIÈRE VÉRIFICATION :**
• L'adresse est-elle correcte ?
• S'agit-il bien d'une adresse USDT TRC20 ?
• Avez-vous accès à cette adresse ?

❌ **ATTENTION : Cette action est irréversible !**
        """,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

    # Stocker temporairement l'adresse
    context.user_data['withdraw_address'] = address
    return ConversationHandler.END

# === GESTION DES CALLBACKS ===

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestionnaire principal des callbacks"""
    query = update.callback_query
    await query.answer()

    data = query.data

    # Vérifier si c'est une action admin
    if data.startswith("admin_"):
        if not is_admin(update.effective_user.id):
            await query.edit_message_text("❌ Accès refusé.")
            return

        if data == "admin_menu":
            await show_admin_menu(update, context)
        elif data == "admin_deposits":
            await show_admin_deposits(update, context)
        elif data == "admin_withdrawals":
            await show_admin_withdrawals(update, context)
        elif data == "admin_stats":
            await show_admin_stats(update, context)
        elif data == "admin_users":
            await show_admin_users(update, context)
        elif data == "admin_support":
            await show_admin_support_tickets(update, context)
        elif data == "admin_security_logs":
            await show_admin_security_logs(update, context)
        elif data == "admin_to_user":
            # Passer en mode utilisateur
            user = get_user_by_telegram_id(update.effective_user.id)
            if user:
                await show_main_menu(update, context, user)
            else:
                await query.edit_message_text("❌ Utilisateur non trouvé.")
        return

    # Actions de validation admin avec sécurité renforcée
    if data.startswith("approve_deposit_"):
        admin_user_id = update.effective_user.id
        
        # Double vérification de sécurité
        if not is_admin(admin_user_id):
            await query.edit_message_text("🚫 Accès refusé - Privilèges administrateur requis")
            log_admin_action(admin_user_id, "UNAUTHORIZED_DEPOSIT_APPROVAL", f"Tentative d'approbation de dépôt par utilisateur non autorisé: {admin_user_id}")
            return
            
        # Vérification de la cohérence de la session
        if update.effective_user.id != admin_user_id:
            await query.edit_message_text("🚫 Erreur de session - Reconnectez-vous")
            log_admin_action(admin_user_id, "ADMIN_SESSION_MISMATCH", "Incohérence de session lors de l'approbation de dépôt")
            return

        try:
            transaction_id = int(data.split("_")[-1])
            success, message = approve_deposit(transaction_id, admin_user_id)

            if success:
                await query.edit_message_text(f"✅ {message}")
                # Retourner au menu des dépôts après 2 secondes
                await asyncio.sleep(2)
                await show_admin_deposits(update, context)
            else:
                await query.edit_message_text(f"❌ {message}")
                
        except ValueError:
            await query.edit_message_text("❌ ID de transaction invalide")
        except Exception as e:
            await query.edit_message_text(f"❌ Erreur système: {str(e)}")
            
        return

    elif data.startswith("reject_deposit_"):
        admin_user_id = update.effective_user.id
        
        # Vérification sécurisée pour rejet de dépôt
        if not is_admin(admin_user_id):
            await query.edit_message_text("🚫 Accès refusé - Privilèges administrateur requis")
            log_admin_action(admin_user_id, "UNAUTHORIZED_DEPOSIT_REJECTION", f"Tentative de rejet de dépôt par utilisateur non autorisé: {admin_user_id}")
            return
            
        # Vérification de l'intégrité de la session
        if update.effective_user.id != admin_user_id:
            await query.edit_message_text("🚫 Session invalide - Reconnectez-vous")
            log_admin_action(admin_user_id, "ADMIN_SESSION_INVALID_REJECTION", "Session invalide lors du rejet de dépôt")
            return

        try:
            transaction_id = int(data.split("_")[-1])
            success, message = reject_deposit(transaction_id, "Vérification échouée - Hash invalide ou suspect", admin_user_id)

            if success:
                await query.edit_message_text(f"❌ {message}")
                await asyncio.sleep(2)
                await show_admin_deposits(update, context)
            else:
                await query.edit_message_text(f"❌ {message}")
                
        except ValueError:
            await query.edit_message_text("❌ ID de transaction invalide")
        except Exception as e:
            await query.edit_message_text(f"❌ Erreur système: {str(e)}")
            
        return

    elif data.startswith("approve_withdrawal_"):
        admin_user_id = update.effective_user.id
        if not is_admin(admin_user_id):
            await query.edit_message_text("🚫 Accès refusé - Privilèges administrateur requis")
            log_admin_action(admin_user_id, "UNAUTHORIZED_ACCESS_ATTEMPT", "Tentative d'approbation de retrait")
            return

        try:
            transaction_id = int(data.split("_")[-1])
            success, message = approve_withdrawal(transaction_id, admin_user_id)

            if success:
                await query.edit_message_text(f"✅ {message}")
                await asyncio.sleep(2)
                await show_admin_withdrawals(update, context)
            else:
                await query.edit_message_text(f"❌ {message}")
                
        except ValueError:
            await query.edit_message_text("❌ ID de transaction invalide")
        except Exception as e:
            await query.edit_message_text(f"❌ Erreur système: {str(e)}")
            
        return

    elif data.startswith("reject_withdrawal_"):
        if not is_admin(update.effective_user.id):
            await query.edit_message_text("❌ Accès refusé.")
            return

        transaction_id = int(data.split("_")[-1])
        success, message = reject_withdrawal(transaction_id, "Retrait refusé")

        if success:
            await query.edit_message_text(f"❌ {message}")
            # Retourner au menu des retraits après 2 secondes
            await asyncio.sleep(2)
            await show_admin_withdrawals(update, context)
        else:
            await query.edit_message_text(f"❌ {message}")
        return

    elif data.startswith("support_reply_"):
        if not is_admin(update.effective_user.id):
            await query.edit_message_text("❌ Accès refusé.")
            return

        ticket_id = int(data.split("_")[-1])
        context.user_data['support_ticket_reply'] = ticket_id
        await query.edit_message_text(
            f"📝 **RÉPONDRE AU TICKET #{ticket_id}**\n\n"
            "Tapez votre réponse :"
        )
        return

    elif data.startswith("support_close_"):
        if not is_admin(update.effective_user.id):
            await query.edit_message_text("❌ Accès refusé.")
            return

        ticket_id = int(data.split("_")[-1])
        success, message = close_support_ticket(ticket_id)

        if success:
            await query.edit_message_text(f"✅ {message}")
            await asyncio.sleep(2)
            await show_admin_support_tickets(update, context)
        else:
            await query.edit_message_text(f"❌ {message}")
        return

    user = get_user_by_telegram_id(update.effective_user.id)

    if data == "main_menu":
        await start(update, context)

    elif data == "about":
        keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        message = """
🚀 **INVESTCRYPTO PRO**
*La plateforme d'investissement crypto nouvelle génération*

🎯 **Notre Mission :**
Démocratiser l'investissement crypto et offrir des rendements exceptionnels à tous nos utilisateurs.

📈 **Nos Services :**

**Plans ROI :** 5% à 15% par jour
• Profits quotidiens automatiques
• Capital + intérêts garantis
• Durées de 30 à 90 jours

**Staking Crypto :** 12% à 25% par an
• Sécurisé par la blockchain
• Récompenses proportionnelles
• Flexibilité de durée

**Crowdfunding :** 18% à 25% de retour
• Projets vérifiés et rentables
• Impact réel sur l'économie
• Diversification du portfolio

**Plans Gelés :** Jusqu'à 400% sur 12 mois
• Investissements long terme
• Rendements exceptionnels
• Sécurité maximale

🔒 **Sécurité :**
• Fonds en cold storage
• Vérifications KYC strictes
• Chiffrement de niveau bancaire
• Audits de sécurité réguliers

💎 **Avantages :**
• Investissement minimum : 20 USDT
• Support client 24/7
• Interface simple et intuitive
• Retraits rapides (24h max)

📞 **Support :** @InvestCryptoPro_Support
🌐 **Site web :** investcryptopro.com
        """

        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

    elif data == "wallet":
        await show_wallet(update, context)

    elif data == "roi_plans":
        await show_roi_plans(update, context)

    elif data == "projects":
        await show_projects(update, context)

    elif data == "staking_plans":
        await show_staking_plans(update, context)

    elif data == "frozen_plans":
        await show_frozen_plans(update, context)

    elif data == "my_investments":
        await show_my_investments(update, context)

    elif data == "referral":
        await show_referral_system(update, context)

    elif data == "notifications":
        await show_notifications(update, context)

    elif data == "profile":
        await show_profile(update, context)

    elif data == "help":
        await show_help(update, context)

    elif data == "deposit":
        await deposit_start(update, context)

    elif data == "withdraw":
        await withdraw_start(update, context)

    elif data.startswith('confirm_withdraw_'):
        await process_withdrawal_confirmation(update, context, data)

    elif data.startswith('invest_staking_'):
        await invest_staking_start(update, context)

    elif data.startswith('invest_project_'):
        await invest_project_start(update, context)

    elif data.startswith('invest_frozen_'):
        await invest_frozen_start(update, context)

    elif data == "investment_details_roi":
        await show_investment_details_roi(update, context)

    elif data == "investment_details_staking":
        await show_investment_details_staking(update, context)

    elif data == "investment_details_frozen":
        await show_investment_details_frozen(update, context)

    elif data == "share_referral":
        await share_referral_link(update, context)

    elif data == "referral_rewards":
        await show_referral_rewards(update, context)

    elif data == "transaction_history":
        await show_transaction_history(update, context)

    elif data == "beginner_guide":
        await show_beginner_guide(update, context)

    elif data == "faq":
        await show_faq(update, context)

    elif data == "security_settings":
        await show_security_settings(update, context)
        
    elif data == "2fa_settings":
        await show_2fa_settings(update, context)
        
    elif data == "security_logs":
        await show_security_logs(update, context)
        
    elif data == "change_password_start":
        await show_change_password_start(update, context)
        
    elif data == "enable_2fa_start":
        await enable_2fa_telegram(update, context)
        
    elif data == "disable_2fa_confirm":
        await disable_2fa_telegram(update, context)

    elif data == "full_history":
        await show_full_history(update, context)

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
        message += "😔 Aucune notification pour le moment.\n\n"
        message += "Les notifications apparaîtront ici pour :\n"
        message += "• Confirmations de dépôts/retraits\n"
        message += "• Profits d'investissements\n"
        message += "• Fins de plans\n"
        message += "• Nouveautés de la plateforme"

    await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Afficher le profil utilisateur"""
    user = get_user_by_telegram_id(update.effective_user.id)

    if not user:
        await update.callback_query.edit_message_text("❌ Veuillez vous connecter d'abord.")
        return

    conn = get_db_connection()

    # Stats utilisateur
    total_investments = conn.execute('''
        SELECT COUNT(*) as count, COALESCE(SUM(amount), 0) as total
        FROM user_investments 
        WHERE user_id = ?
    ''', (user['id'],)).fetchone()

    total_earnings = conn.execute('''
        SELECT COALESCE(SUM(total_earned), 0) as total
        FROM user_investments 
        WHERE user_id = ?
    ''', (user['id'],)).fetchone()

    referral_count = conn.execute('''
        SELECT COUNT(*) as count
        FROM users 
        WHERE referred_by = ?
    ''', (user['referral_code'],)).fetchone()

    conn.close()

    keyboard = [
        [InlineKeyboardButton("🔐 Sécurité du compte", callback_data="security_settings")],
        [InlineKeyboardButton("📋 Historique complet", callback_data="full_history")],
        [InlineKeyboardButton("🔙 Menu principal", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Calcul du niveau utilisateur
    if total_investments['total'] < 100:
        level = "🥉 Bronze"
    elif total_investments['total'] < 1000:
        level = "🥈 Argent"
    elif total_investments['total'] < 5000:
        level = "🥇 Or"
    else:
        level = "💎 Diamant"

    # Formatage sécurisé des dates
    try:
        created_date = datetime.fromisoformat(user['created_at'].replace('Z', '+00:00')).strftime('%d/%m/%Y')
    except:
        created_date = "Non disponible"

    # Statut de sécurité
    security_status = "🔒 Sécurisé" if user['two_fa_enabled'] else "⚠️ Non sécurisé"

    # Sécuriser les valeurs pour éviter les erreurs Markdown - échapper les caractères spéciaux
    first_name = str(user['first_name'] or 'Utilisateur').replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(']', '\\]').replace('(', '\\(').replace(')', '\\)')
    last_name = str(user['last_name'] or '').replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(']', '\\]').replace('(', '\\(').replace(')', '\\)')
    email = str(user['email'] or 'Non renseigné').replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(']', '\\]').replace('(', '\\(').replace(')', '\\)')
    kyc_status = str(user['kyc_status'] or 'pending').replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(']', '\\]').replace('(', '\\(').replace(')', '\\)')
    referred_by = str(user['referred_by'] or 'Aucun').replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(']', '\\]').replace('(', '\\(').replace(')', '\\)')

    message = f"""👤 *MON PROFIL*

*Informations personnelles :*
• Nom : {first_name} {last_name}
• Email : {email}
• Inscription : {created_date}

*Statut compte :*
• Niveau : {level}
• KYC : {kyc_status}
• Sécurité : {security_status}
• Solde : {user['balance']:.2f} USDT

*Statistiques :*
• Total investi : {total_investments['total']:.2f} USDT
• Total gagné : {total_earnings['total']:.2f} USDT
• Investissements : {total_investments['count']}
• Filleuls : {referral_count['count']}

*Parrainage :*
• Code : `{user['referral_code']}`
• Parrainé par : {referred_by}"""

    await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Afficher l'aide"""
    keyboard = [
        [InlineKeyboardButton("💬 Support direct", url="https://t.me/InvestCryptoPro_Support")],
        [InlineKeyboardButton("📚 Guide débutant", callback_data="beginner_guide")],
        [InlineKeyboardButton("❓ FAQ", callback_data="faq")],
        [InlineKeyboardButton("🔙 Menu principal", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message = """❓ *CENTRE D'AIDE*

🚀 *Comment commencer :*
1\\. Effectuez votre premier dépôt \\(min\\. 10 USDT\\)
2\\. Choisissez un plan d'investissement
3\\. Regardez vos profits grandir \\!

💡 *Questions fréquentes :*

*Q: Quand reçois\\-je mes profits ?*
R: Les profits ROI sont crédités automatiquement chaque jour à minuit UTC\\.

*Q: Puis\\-je retirer à tout moment ?*
R: Oui, votre solde disponible peut être retiré 24h/24\\.

*Q: Y a\\-t\\-il des frais cachés ?*
R: Non, seuls 2 USDT de frais s'appliquent aux retraits\\.

*Q: Mes fonds sont\\-ils sécurisés ?*
R: Oui, nous utilisons un stockage à froid et des audits réguliers\\.

*Q: Comment fonctionne le parrainage ?*
R: Partagez votre code et gagnez sur chaque nouveau membre \\!

📞 *Besoin d'aide personnalisée ?*
Contactez notre support 24/7 :
@InvestCryptoPro\\_Support

⏰ *Temps de réponse moyen : 2 heures*"""

    await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='MarkdownV2')

async def process_withdrawal_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
    """Traiter la confirmation de retrait"""
    user = get_user_by_telegram_id(update.effective_user.id)

    # Extraire les données
    parts = data.split('_')
    amount = float(parts[2])
    address = parts[3]

    conn = get_db_connection()

    # Vérifier le solde une dernière fois
    current_user = conn.execute('SELECT balance FROM users WHERE id = ?', (user['id'],)).fetchone()
    if current_user['balance'] < amount:
        await update.callback_query.edit_message_text(
            "❌ Solde insuffisant. Votre solde a peut-être changé.",
            parse_mode='Markdown'
        )
        return

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

    # Notification admin
    try:
        from telegram_bot import notify_withdrawal_request
        notify_withdrawal_request(user['id'], amount, address, withdrawal_id)
    except:
        pass

    add_notification(
        user['id'],
        'Retrait en cours de traitement',
        f'Votre retrait de {amount} USDT vers {address[:10]}... est en cours de traitement.',
        'info'
    )

    net_amount = amount - 2

    await update.callback_query.edit_message_text(
        f"""
✅ **RETRAIT CONFIRMÉ**

💰 **Montant :** {amount:.2f} USDT
💵 **Net (après frais) :** {net_amount:.2f} USDT
📍 **Adresse :** `{address}`
🆔 **Référence :** #{withdrawal_id}

⏰ **Traitement :** Sous 24h maximum
🔔 **Suivi :** Vous recevrez une notification

💡 **Le montant a été débité de votre solde pour sécuriser la transaction.**

Utilisez /start pour retourner au menu.
        """,
        parse_mode='Markdown'
    )

async def invest_staking_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Début investissement staking"""
    await update.callback_query.answer()
    plan_id = update.callback_query.data.split('_')[-1]

    conn = get_db_connection()
    plan = conn.execute('SELECT * FROM staking_plans WHERE id = ?', (plan_id,)).fetchone()
    conn.close()

    if not plan:
        await update.callback_query.edit_message_text("❌ Plan de staking non trouvé.")
        return

    message = f"""
💎 **INVESTISSEMENT STAKING - {plan['name'].upper()}**

📈 **Rendement annuel :** {plan['annual_rate']*100:.1f}%
⏰ **Durée :** {plan['duration_days']} jours
💰 **Limites :** {plan['min_amount']:.0f} - {plan['max_amount']:.0f} USDT

Cette fonctionnalité sera bientôt disponible !
    """

    keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="staking_plans")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def invest_project_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Début investissement projet"""
    await update.callback_query.answer()
    project_id = update.callback_query.data.split('_')[-1]

    conn = get_db_connection()
    project = conn.execute('SELECT * FROM projects WHERE id = ?', (project_id,)).fetchone()
    conn.close()

    if not project:
        await update.callback_query.edit_message_text("❌ Projet non trouvé.")
        return

    message = f"""
🎯 **INVESTISSEMENT PROJET - {project['title'].upper()}**

📊 **Rendement attendu :** {project['expected_return']*100:.1f}%
💰 **Limites :** {project['min_investment']:.0f} - {project['max_investment']:.0f} USDT

Cette fonctionnalité sera bientôt disponible !
    """

    keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="projects")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def invest_frozen_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Début investissement gelé"""
    await update.callback_query.answer()
    plan_id = update.callback_query.data.split('_')[-1]

    conn = get_db_connection()
    plan = conn.execute('SELECT * FROM frozen_plans WHERE id = ?', (plan_id,)).fetchone()
    conn.close()

    if not plan:
        await update.callback_query.edit_message_text("❌ Plan gelé non trouvé.")
        return

    message = f"""
🧊 **INVESTISSEMENT GELÉ - {plan['name'].upper()}**

🎯 **Retour total :** {plan['total_return_rate']*100:.1f}%
⏰ **Durée :** {plan['duration_days']} jours
💰 **Limites :** {plan['min_amount']:.0f} - {plan['max_amount']:.0f} USDT

Cette fonctionnalité sera bientôt disponible !
    """

    keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="frozen_plans")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def show_investment_details_roi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Afficher détails investissements ROI"""
    await update.callback_query.answer()
    user = get_user_by_telegram_id(update.effective_user.id)

    conn = get_db_connection()
    investments = conn.execute('''
        SELECT ui.*, rp.name as plan_name, rp.daily_rate
        FROM user_investments ui
        JOIN roi_plans rp ON ui.plan_id = rp.id
        WHERE ui.user_id = ? AND ui.is_active = 1
        ORDER BY ui.start_date DESC
        LIMIT 5
    ''', (user['id'],)).fetchall()
    conn.close()

    message = "📈 **DÉTAILS INVESTISSEMENTS ROI**\n\n"

    if investments:
        for inv in investments:
            days_remaining = (datetime.fromisoformat(inv['end_date'].replace('Z', '+00:00')) - datetime.now()).days
            message += f"💎 **{inv['plan_name']}**\n"
            message += f"💰 {inv['amount']:.2f} USDT\n"
            message += f"📊 {inv['daily_profit']:.2f} USDT/jour\n"
            message += f"⏰ {max(0, days_remaining)} jours restants\n"
            message += f"🎁 Gagné : {inv['total_earned']:.2f} USDT\n\n"
    else:
        message += "😔 Aucun investissement ROI actif."

    keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="my_investments")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def show_investment_details_staking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Afficher détails staking"""
    await update.callback_query.answer()

    message = """
💎 **DÉTAILS STAKING**

Cette fonctionnalité sera bientôt disponible !
Vous pourrez voir ici tous vos investissements de staking.
    """

    keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="my_investments")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def show_investment_details_frozen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Afficher détails gelés"""
    await update.callback_query.answer()

    message = """
🧊 **DÉTAILS PLANS GELÉS**

Cette fonctionnalité sera bientôt disponible !
Vous pourrez voir ici tous vos investissements gelés.
    """

    keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="my_investments")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def share_referral_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Partager le lien de parrainage"""
    await update.callback_query.answer()
    user = get_user_by_telegram_id(update.effective_user.id)

    message = f"""
📤 **PARTAGER MON LIEN DE PARRAINAGE**

🎁 **Votre code :** `{user['referral_code']}`

📋 **Message à partager :**

🚀 Rejoignez InvestCrypto Pro !
💰 Plateforme d'investissement crypto sécurisée
🎁 Bonus de bienvenue : 10 USDT offerts
💎 Plans ROI, Staking, Projets et plus !

👥 Utilisez mon code de parrainage : `{user['referral_code']}`
🤖 Bot Telegram : @InvestCryptoProBot

Commencez à investir dès maintenant ! 🚀
    """

    keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="referral")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def show_referral_rewards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Afficher les récompenses de parrainage"""
    await update.callback_query.answer()

    message = """
🏆 **PROGRAMME DE RÉCOMPENSES**

💰 **Récompenses immédiates :**
• 5 USDT par nouveau filleul
• 10 USDT bonus pour votre filleul

📈 **Commissions sur investissements :**
• 2% sur tous les investissements de vos filleuls
• Commissions versées instantanément

🎯 **Bonus mensuels :**
• 1-5 filleuls : 10 USDT bonus
• 6-10 filleuls : 25 USDT bonus
• 11-25 filleuls : 50 USDT bonus
• 25+ filleuls : 100 USDT bonus

👑 **Statuts VIP :**
• Argent (10 filleuls) : +0.5% commission
• Or (25 filleuls) : +1% commission
• Diamant (50 filleuls) : +2% commission
    """

    keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="referral")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def show_transaction_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Afficher l'historique des transactions"""
    await update.callback_query.answer()
    user = get_user_by_telegram_id(update.effective_user.id)

    conn = get_db_connection()
    transactions = conn.execute('''
        SELECT * FROM transactions 
        WHERE user_id = ? 
        ORDER BY created_at DESC 
        LIMIT 10
    ''', (user['id'],)).fetchall()
    conn.close()

    message = "📋 **HISTORIQUE DES TRANSACTIONS**\n\n"

    if transactions:
        for tx in transactions:
            status_emoji = "✅" if tx['status'] == 'completed' else "⏳" if tx['status'] == 'pending' else "❌"
            type_emoji = "📥" if tx['type'] == 'deposit' else "📤" if tx['type'] == 'withdrawal' else "💎"

            try:
                date_str = datetime.fromisoformat(tx['created_at'].replace('Z', '+00:00')).strftime('%d/%m %H:%M')
            except:
                date_str = "Non disponible"

            message += f"{status_emoji} {type_emoji} **{tx['amount']:.2f} USDT**\n"
            message += f"📅 {date_str} | {tx['type'].title()}\n"
            message += f"🆔 {tx['transaction_hash'][:16]}...\n\n"
    else:
        message += "😔 Aucune transaction pour le moment."

    keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="wallet")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def show_beginner_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Afficher le guide débutant"""
    await update.callback_query.answer()

    message = """
📚 **GUIDE DÉBUTANT**

🚀 **Étapes pour commencer :**

1️⃣ **Effectuez votre premier dépôt**
   • Minimum : 10 USDT
   • Réseau : TRC20 uniquement
   • Vérification sous 24h

2️⃣ **Choisissez un plan d'investissement**
   • Plans ROI : 5-15% par jour
   • Staking : 12-25% par an
   • Projets : 18-25% de retour

3️⃣ **Suivez vos profits**
   • Gains crédités automatiquement
   • Notifications en temps réel
   • Historique complet

4️⃣ **Parrainez vos amis**
   • 5 USDT par filleul
   • 2% de commission
   • Bonus mensuels

💡 **Conseils :**
• Commencez petit pour tester
• Diversifiez vos investissements
• Réinvestissez vos profits
• Utilisez le parrainage
    """

    keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="help")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def show_faq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Afficher la FAQ"""
    await update.callback_query.answer()

    message = """
❓ **QUESTIONS FRÉQUENTES**

**Q: Combien puis-je gagner ?**
R: Cela dépend de votre investissement. Nos plans ROI offrent 5-15% par jour.

**Q: Quand reçois-je mes profits ?**
R: Les profits ROI sont crédités automatiquement chaque jour à minuit UTC.

**Q: Puis-je retirer à tout moment ?**
R: Oui, votre solde disponible peut être retiré 24h/24 avec 2 USDT de frais.

**Q: Mes fonds sont-ils sécurisés ?**
R: Oui, nous utilisons un stockage à froid et des audits de sécurité réguliers.

**Q: Comment fonctionne le parrainage ?**
R: Partagez votre code et gagnez 5 USDT par nouveau membre + 2% sur leurs investissements.

**Q: Que se passe-t-il si j'oublie mon mot de passe ?**
R: Contactez le support avec votre ID Telegram pour récupérer votre compte.

**Q: Y a-t-il des frais cachés ?**
R: Non, seuls 2 USDT de frais s'appliquent aux retraits.
    """

    keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="help")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def show_security_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Afficher les paramètres de sécurité"""
    await update.callback_query.answer()
    user = get_user_by_telegram_id(update.effective_user.id)

    if not user:
        await update.callback_query.edit_message_text("❌ Veuillez vous connecter d'abord.")
        return

    keyboard = [
        [InlineKeyboardButton("🔑 Changer mot de passe", callback_data="change_password_start")],
        [InlineKeyboardButton("🛡️ Authentification 2FA", callback_data="2fa_settings")],
        [InlineKeyboardButton("📜 Logs de sécurité", callback_data="security_logs")],
        [InlineKeyboardButton("🔙 Retour au profil", callback_data="profile")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Statut 2FA
    fa_status = "✅ Activé" if user['two_fa_enabled'] else "❌ Désactivé"
    
    message = f"""
🔐 **PARAMÈTRES DE SÉCURITÉ**

👤 **Compte :** {user['first_name']} {user['last_name']}
📧 **Email :** {user['email']}

🛡️ **État de la sécurité :**
• Authentification 2FA : {fa_status}
• Connexion Telegram : ✅ Sécurisée
• Dernière connexion : {user.get('last_login', 'Inconnue')}

🔒 **Actions disponibles :**
• Modifier votre mot de passe
• Gérer l'authentification 2FA
• Consulter les logs de sécurité

⚠️ **Important :** Votre compte est déjà sécurisé par Telegram, mais nous recommandons d'activer la 2FA pour une protection maximale.
    """

    await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def show_2fa_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Afficher les paramètres 2FA"""
    await update.callback_query.answer()
    user = get_user_by_telegram_id(update.effective_user.id)

    if user.get('two_fa_enabled'):
        keyboard = [
            [InlineKeyboardButton("❌ Désactiver 2FA", callback_data="disable_2fa_confirm")],
            [InlineKeyboardButton("🔙 Retour sécurité", callback_data="security_settings")]
        ]
        
        message = """
🛡️ **AUTHENTIFICATION 2FA ACTIVÉE**

✅ **Statut :** Votre compte est protégé par l'authentification à deux facteurs.

🔒 **Protection active :**
• Connexions sécurisées
• Protection contre les accès non autorisés
• Sécurité renforcée pour les transactions

⚠️ **Désactivation :** Si vous souhaitez désactiver la 2FA, vous devrez confirmer cette action.
        """
    else:
        keyboard = [
            [InlineKeyboardButton("✅ Activer 2FA", callback_data="enable_2fa_start")],
            [InlineKeyboardButton("🔙 Retour sécurité", callback_data="security_settings")]
        ]
        
        message = """
🛡️ **AUTHENTIFICATION 2FA DÉSACTIVÉE**

❌ **Statut :** Votre compte n'est pas protégé par la 2FA.

🔐 **Avantages de la 2FA :**
• Protection supplémentaire contre le piratage
• Sécurité renforcée pour vos fonds
• Conformité aux meilleures pratiques de sécurité

📱 **Applications recommandées :**
• Google Authenticator
• Authy
• Microsoft Authenticator

💡 **Recommandation :** Activez la 2FA pour sécuriser votre compte.
        """

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def show_security_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Afficher les logs de sécurité utilisateur"""
    await update.callback_query.answer()
    user = get_user_by_telegram_id(update.effective_user.id)

    conn = get_db_connection()
    
    # Récupérer les logs de sécurité de l'utilisateur
    try:
        logs = conn.execute('''
            SELECT * FROM security_logs 
            WHERE user_id = ? 
            ORDER BY created_at DESC 
            LIMIT 10
        ''', (user['id'],)).fetchall()
    except:
        logs = []
    
    conn.close()

    keyboard = [[InlineKeyboardButton("🔙 Retour sécurité", callback_data="security_settings")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message = "📜 **LOGS DE SÉCURITÉ** (10 derniers)\n\n"

    if logs:
        for log in logs:
            try:
                date_str = datetime.fromisoformat(log['created_at'].replace('Z', '+00:00')).strftime('%d/%m %H:%M')
            except:
                date_str = "N/A"

            action_emoji = "🔐" if "password" in log['action'] else "🛡️" if "2fa" in log['action'] else "🔑"
            
            message += f"{action_emoji} **{log['action'].replace('_', ' ').title()}**\n"
            message += f"📅 {date_str}\n"
            if log['details']:
                message += f"📝 {log['details']}\n"
            if log['ip_address']:
                message += f"🌐 IP: {log['ip_address']}\n"
            message += "\n"
    else:
        message += "Aucun événement de sécurité enregistré pour le moment.\n\n"
        message += "Les événements suivants seront enregistrés :\n"
        message += "• Changements de mot de passe\n"
        message += "• Activation/désactivation 2FA\n"
        message += "• Connexions suspectes"

    # Limiter la taille du message
    if len(message) > 4000:
        message = message[:3900] + "\n\n✂️ Message tronqué..."

    await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def show_full_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Afficher l'historique complet"""
    await update.callback_query.answer()

    message = """
📋 **HISTORIQUE COMPLET**

Cette fonctionnalité sera bientôt disponible !

Vous pourrez voir ici :
• Tous vos investissements
• Historique des profits
• Transactions détaillées
• Rapports mensuels

Pour le moment, utilisez les sections individuelles pour voir vos données.
    """

    keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="profile")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

# === FONCTIONS ADMINISTRATEUR ===

async def show_admin_deposits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Afficher les dépôts en attente"""
    await update.callback_query.answer()

    deposits = get_pending_deposits()

    if not deposits:
        keyboard = [[InlineKeyboardButton("🔙 Retour admin", callback_data="admin_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.callback_query.edit_message_text(
            "✅ **Aucun dépôt en attente**",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return

    keyboard = []
    message = "💳 **DÉPÔTS EN ATTENTE**\n\n"

    for deposit in deposits[:5]:  # Limiter à 5 pour éviter un message trop long
        user_name = f"{deposit['first_name']} {deposit['last_name'] or ''}"
        try:
            date_str = datetime.fromisoformat(deposit['created_at'].replace('Z', '+00:00')).strftime('%d/%m %H:%M')
        except:
            date_str = "Non disponible"

        message += f"👤 **{user_name}**\n"
        message += f"💰 {deposit['amount']:.2f} USDT\n"
        message += f"📅 {date_str}\n"
        message += f"🔗 `{deposit['transaction_hash'][:20]}...`\n\n"

        keyboard.append([
            InlineKeyboardButton(f"✅ Approuver #{deposit['id']}", callback_data=f"approve_deposit_{deposit['id']}"),
            InlineKeyboardButton(f"❌ Rejeter #{deposit['id']}", callback_data=f"reject_deposit_{deposit['id']}")
        ])

    if len(deposits) > 5:
        message += f"... et {len(deposits) - 5} autres dépôts"

    keyboard.append([InlineKeyboardButton("🔙 Retour admin", callback_data="admin_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def show_admin_withdrawals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Afficher les retraits en attente"""
    await update.callback_query.answer()

    withdrawals = get_pending_withdrawals()

    if not withdrawals:
        keyboard = [[InlineKeyboardButton("🔙 Retour admin", callback_data="admin_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.callback_query.edit_message_text(
            "✅ **Aucun retrait en attente**",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return

    keyboard = []
    message = "💸 **RETRAITS EN ATTENTE**\n\n"

    for withdrawal in withdrawals[:5]:  # Limiter à 5 pour éviter un message trop long
        user_name = f"{withdrawal['first_name']} {withdrawal['last_name'] or ''}"
        try:
            date_str = datetime.fromisoformat(withdrawal['created_at'].replace('Z', '+00:00')).strftime('%d/%m %H:%M')
        except:
            date_str = "Non disponible"

        # Extraire l'adresse du hash
        address = withdrawal['transaction_hash'].split('|')[0] if '|' in withdrawal['transaction_hash'] else "Non disponible"

        message += f"👤 **{user_name}**\n"
        message += f"💰 {withdrawal['amount']:.2f} USDT\n"
        message += f"📅 {date_str}\n"
        message += f"📍 `{address[:20]}...`\n\n"

        keyboard.append([
            InlineKeyboardButton(f"✅ Traiter #{withdrawal['id']}", callback_data=f"approve_withdrawal_{withdrawal['id']}"),
            InlineKeyboardButton(f"❌ Rejeter #{withdrawal['id']}", callback_data=f"reject_withdrawal_{withdrawal['id']}")
        ])

    if len(withdrawals) > 5:
        message += f"... et {len(withdrawals) - 5} autres retraits"

    keyboard.append([InlineKeyboardButton("🔙 Retour admin", callback_data="admin_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def show_admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Afficher les statistiques administrateur"""
    await update.callback_query.answer()

    conn = get_db_connection()

    # Statistiques générales
    total_users = conn.execute('SELECT COUNT(*) as count FROM users').fetchone()['count']
    total_deposits = conn.execute('SELECT COALESCE(SUM(amount), 0) as total FROM transactions WHERE type = "deposit" AND status = "completed"').fetchone()['total']
    total_withdrawals = conn.execute('SELECT COALESCE(SUM(amount), 0) as total FROM transactions WHERE type = "withdrawal" AND status = "completed"').fetchone()['total']
    total_investments = conn.execute('SELECT COALESCE(SUM(amount), 0) as total FROM user_investments').fetchone()['total']

    # Statistiques du jour
    today = datetime.now().strftime('%Y-%m-%d')
    daily_users = conn.execute('SELECT COUNT(*) as count FROM users WHERE DATE(created_at) = ?', (today,)).fetchone()['count']
    daily_deposits = conn.execute('SELECT COALESCE(SUM(amount), 0) as total FROM transactions WHERE type = "deposit" AND DATE(created_at) = ?', (today,)).fetchone()['total']

    conn.close()

    keyboard = [[InlineKeyboardButton("🔙 Retour admin", callback_data="admin_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message = f"""
📊 **STATISTIQUES PLATEFORME**

👥 **Utilisateurs :**
• Total : {total_users}
• Nouveaux aujourd'hui : {daily_users}

💰 **Finances :**
• Dépôts totaux : {total_deposits:.2f} USDT
• Retraits totaux : {total_withdrawals:.2f} USDT
• Investissements : {total_investments:.2f} USDT

📈 **Aujourd'hui :**
• Dépôts : {daily_deposits:.2f} USDT
• Nouveaux utilisateurs : {daily_users}

💼 **Solde plateforme :**
• Liquidité : {total_deposits - total_withdrawals:.2f} USDT
    """

    await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def show_admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Afficher les utilisateurs récents"""
    await update.callback_query.answer()
    
    admin_user_id = update.effective_user.id
    if not is_admin(admin_user_id):
        await update.callback_query.edit_message_text("🚫 Accès refusé")
        return
    
    log_admin_action(admin_user_id, "VIEW_USERS", "Consultation de la liste des utilisateurs")

    conn = get_db_connection()
    recent_users = conn.execute('''
        SELECT first_name, last_name, balance, created_at, kyc_status
        FROM users 
        ORDER BY created_at DESC 
        LIMIT 10
    ''').fetchall()
    conn.close()

    keyboard = [[InlineKeyboardButton("🔙 Retour admin", callback_data="admin_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message = "👥 **UTILISATEURS RÉCENTS**\n\n"

    for user in recent_users:
        try:
            date_str = datetime.fromisoformat(user['created_at'].replace('Z', '+00:00')).strftime('%d/%m')
        except:
            date_str = "N/A"

        status_emoji = "✅" if user['kyc_status'] == 'verified' else "⏳" if user['kyc_status'] == 'pending' else "❌"
        
        message += f"👤 {user['first_name']} {user['last_name'] or ''}\n"
        message += f"💰 {user['balance']:.2f} USDT | 📅 {date_str} | {status_emoji} {user['kyc_status']}\n\n"

    await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def show_admin_security_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Afficher les logs de sécurité"""
    await update.callback_query.answer()
    
    admin_user_id = update.effective_user.id
    if not is_admin(admin_user_id):
        await update.callback_query.edit_message_text("🚫 Accès refusé")
        return
    
    log_admin_action(admin_user_id, "VIEW_SECURITY_LOGS", "Consultation des logs de sécurité")

    conn = get_db_connection()
    
    try:
        logs = conn.execute('''
            SELECT * FROM admin_logs 
            ORDER BY timestamp DESC 
            LIMIT 15
        ''').fetchall()
    except:
        # Table n'existe pas encore
        logs = []
    
    conn.close()

    keyboard = [[InlineKeyboardButton("🔙 Retour admin", callback_data="admin_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message = "🔒 **LOGS DE SÉCURITÉ** (15 derniers)\n\n"

    if logs:
        for log in logs:
            try:
                date_str = datetime.fromisoformat(log['timestamp'].replace('Z', '+00:00')).strftime('%d/%m %H:%M')
            except:
                date_str = "N/A"

            action_emoji = "🔓" if "APPROVED" in log['action'] else "🚫" if "REJECTED" in log['action'] else "👁️" if "VIEW" in log['action'] else "⚠️"
            
            message += f"{action_emoji} **{log['action']}**\n"
            message += f"👤 Admin: {log['admin_id']}\n"
            message += f"📅 {date_str}\n"
            if log['details']:
                message += f"📝 {log['details'][:50]}...\n"
            message += "\n"
    else:
        message += "Aucun log disponible pour le moment."

    # Limiter la taille du message
    if len(message) > 4000:
        message = message[:3900] + "\n\n✂️ Message tronqué..."

    await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def show_admin_support_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Afficher les tickets de support pour l'admin"""
    try:
        conn = get_db_connection()

        # Récupérer les tickets ouverts
        tickets = conn.execute('''
            SELECT st.*, u.first_name, u.last_name, u.email,
                   COUNT(sm.id) as message_count
            FROM support_tickets st
            JOIN users u ON st.user_id = u.id
            LEFT JOIN support_messages sm ON st.id = sm.ticket_id
            WHERE st.status IN ('open', 'user_reply')
            GROUP BY st.id
            ORDER BY st.updated_at DESC
            LIMIT 10
        ''').fetchall()

        if not tickets:
            text = "📋 Aucun ticket de support en attente"
            keyboard = [[InlineKeyboardButton("🔄 Actualiser", callback_data="admin_support_refresh")]]
        else:
            text = f"🎫 *Tickets de Support* ({len(tickets)} en attente)\n\n"

            keyboard = []
            for ticket in tickets:
                status_emoji = "🆕" if ticket['status'] == 'open' else "💬"
                priority_emoji = "🔴" if ticket['priority'] == 'urgent' else "🟡" if ticket['priority'] == 'high' else "🟢"

                text += f"{status_emoji} *#{ticket['id']}* - {ticket['subject'][:30]}...\n"
                text += f"👤 {ticket['first_name']} {ticket['last_name']}\n"
                text += f"📝 {ticket['message_count']} messages • {priority_emoji} {ticket['priority']}\n\n"

                keyboard.append([
                    InlineKeyboardButton(f"📖 Ticket #{ticket['id']}", callback_data=f"admin_ticket_{ticket['id']}")
                ])

            keyboard.append([InlineKeyboardButton("🔄 Actualiser", callback_data="admin_support_refresh")])

        reply_markup = InlineKeyboardMarkup(keyboard)

        # Vérifier si c'est un callback query ou un message normal
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        elif update.message:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

        conn.close()

    except Exception as e:
        error_text = f"❌ Erreur lors de la récupération des tickets: {str(e)}"
        print(f"Erreur show_admin_support_tickets: {e}")

        try:
            if update.callback_query:
                await update.callback_query.answer(error_text)
            elif update.message:
                await update.message.reply_text(error_text)
        except Exception as reply_error:
            print(f"Erreur lors de l'envoi de la réponse d'erreur: {reply_error}")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Annuler une conversation"""
    context.user_data.clear()
    await update.message.reply_text(
        "❌ **Opération annulée**\n\n"
        "Utilisez /start pour retourner au menu principal.",
        parse_mode='Markdown'
    )
    return ConversationHandler.END

# === CONFIGURATION ET DÉMARRAGE ===

def setup_user_telegram_bot():
    """Configure le bot utilisateur"""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN non configuré")
        print("❌ Bot utilisateur non disponible - Token manquant")
        return None

    # Vérifier si les imports Telegram sont disponibles
    if not Application:
        print("❌ Bot utilisateur non disponible - Modules Telegram manquants")
        print("💡 Exécutez: pip install python-telegram-bot")
        return None

    try:
        # Initialiser les colonnes telegram_id si nécessaire
        init_telegram_db()

        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        print(f"✅ Bot utilisateur configuré avec succès")

    except Exception as e:
        logger.error(f"❌ Erreur configuration bot utilisateur: {e}")
        print(f"❌ Erreur configuration bot utilisateur: {e}")
        return None

    # Plus besoin de handlers d'inscription/connexion - authentification automatique via Telegram ID

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

    # Handler pour les réponses de support admin
    async def handle_support_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Gérer les réponses de support admin"""
        if not is_admin(update.effective_user.id):
            return

        if 'support_ticket_reply' in context.user_data:
            ticket_id = context.user_data['support_ticket_reply']
            admin_message = update.message.text

            success, message = reply_to_support_ticket(ticket_id, admin_message)

            if success:
                await update.message.reply_text(f"✅ {message}")
                # Retourner au menu des tickets après la réponse
                await asyncio.sleep(1)
                await show_admin_support_tickets(update, context)
            else:
                await update.message.reply_text(f"❌ {message}")

            del context.user_data['support_ticket_reply']
        else:
            await update.message.reply_text("❌ Aucune action de support en attente.")

    # Ajouter tous les handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(deposit_handler)
    application.add_handler(withdraw_handler)
    application.add_handler(invest_roi_handler)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_support_reply))
    application.add_handler(CallbackQueryHandler(handle_callback))

    # Ajouter le gestionnaire d'erreur
    application.add_error_handler(error_handler)

    return application

# Initialise les tables avec les nouveaux minimums
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Insert top 10 ROI plans - Starting from 20 USDT
    cursor.execute('''
        INSERT OR IGNORE INTO roi_plans (name, description, daily_rate, duration_days, min_amount, max_amount)
        VALUES 
        ('Starter Pro', '🚀 Parfait pour débuter ! 3% quotidien sur 30 jours. Idéal pour tester nos services avec un petit budget.', 0.03, 30, 20, 500),
        ('Rapid Growth', '⚡ Croissance rapide ! 4% par jour pendant 25 jours. Parfait équilibre temps/profit.', 0.04, 25, 20, 800),
        ('Silver Plan', '🥈 Plan argent ! 5% quotidien sur 30 jours. Notre bestseller pour débutants.', 0.05, 30, 20, 1000),
        ('Golden Boost', '🥇 Plan or ! 6% par jour pendant 35 jours. Excellent retour sur investissement.', 0.06, 35, 20, 2000),
        ('Platinum Elite', '💎 Elite platinum ! 7% quotidien sur 40 jours. Pour investisseurs sérieux.', 0.07, 40, 20, 3000),
        ('Diamond Pro', '💍 Diamant professionnel ! 8% par jour pendant 45 jours. Rendement exceptionnel.', 0.08, 45, 20, 5000),
        ('VIP Supreme', '👑 VIP suprême ! 10% quotidien sur 50 jours. Pour les grands investisseurs.', 0.10, 50, 20, 8000),
        ('Royal Master', '🏆 Royal master ! 12% par jour pendant 60 jours. Retour royal garanti.', 0.12, 60, 20, 12000),
        ('Ultra Premium', '⭐ Ultra premium ! 15% quotidien sur 70 jours. Performance maximale.', 0.15, 70, 20, 20000),
        ('Emperor Elite', '👨‍💼 Empereur elite ! 18% par jour pendant 80 jours. Le summum de l''investissement.', 0.18, 80, 20, 50000)
    ''')

    # Insert top 10 staking plans - Starting from 20 USDT
    cursor.execute('''
        INSERT OR IGNORE INTO staking_plans (name, description, duration_days, annual_rate, min_amount, max_amount, penalty_rate)
        VALUES 
        ('Quick Stake', '⚡ Staking rapide 7 jours ! 8% annuel. Parfait pour tester le staking.', 7, 0.08, 20, 300, 0.02),
        ('Flex Stake', '🔄 Staking flexible 15 jours ! 12% annuel. Idéal pour débutants.', 15, 0.12, 20, 500, 0.03),
        ('Standard Stake', '📊 Staking standard 30 jours ! 18% annuel. Notre choix populaire.', 30, 0.18, 20, 1000, 0.04),
        ('Power Stake', '💪 Staking puissant 45 jours ! 22% annuel. Excellent rendement.', 45, 0.22, 20, 2000, 0.05),
        ('Premium Stake', '💎 Staking premium 60 jours ! 28% annuel. Pour investisseurs sérieux.', 60, 0.28, 20, 3000, 0.06),
        ('Elite Stake', '🏆 Staking elite 90 jours ! 35% annuel. Performance exceptionnelle.', 90, 0.35, 20, 5000, 0.07),
        ('Master Stake', '👑 Staking master 120 jours ! 42% annuel. Retour impressionnant.', 120, 0.42, 20, 8000, 0.08),
        ('Royal Stake', '🎖️ Staking royal 150 jours ! 50% annuel. Rendement royal.', 150, 0.50, 20, 12000, 0.09),
        ('Supreme Stake', '⭐ Staking suprême 180 jours ! 60% annuel. Le top du staking.', 180, 0.60, 20, 20000, 0.10),
        ('Ultimate Stake', '🚀 Staking ultimate 365 jours ! 80% annuel. Performance ultime.', 365, 0.80, 20, 50000, 0.12)
    ''')

    # Insert top 10 frozen plans - Starting from 20 USDT
    cursor.execute('''
        INSERT OR IGNORE INTO frozen_plans (name, description, duration_days, total_return_rate, min_amount, max_amount)
        VALUES 
        ('Ice Starter', '🧊 Plan gelé débutant ! 30 jours gelés pour 150% de retour total.', 30, 1.5, 20, 400),
        ('Frost Basic', '❄️ Plan frost basique ! 60 jours gelés pour 180% de retour total.', 60, 1.8, 20, 600),
        ('Freeze Standard', '🥶 Plan freeze standard ! 90 jours gelés pour 220% de retour total.', 90, 2.2, 20, 800),
        ('Glacial Pro', '🏔️ Plan glacial pro ! 120 jours gelés pour 280% de retour total.', 120, 2.8, 20, 1200),
        ('Arctic Elite', '🐧 Plan arctique elite ! 150 jours gelés pour 350% de retour total.', 150, 3.5, 20, 2000),
        ('Polar Premium', '🐻‍❄️ Plan polaire premium ! 180 jours gelés pour 450% de retour total.', 180, 4.5, 20, 3000),
        ('Blizzard VIP', '❄️ Plan blizzard VIP ! 240 jours gelés pour 600% de retour total.', 240, 6.0, 20, 5000),
        ('Absolute Zero', '🌨️ Plan zéro absolu ! 300 jours gelés pour 800% de retour total.', 300, 8.0, 20, 8000),
        ('Eternal Frost', '🧊 Plan gel éternel ! 360 jours gelés pour 1200% de retour total.', 360, 12.0, 20, 15000),
        ('Cosmic Ice', '🌌 Plan glace cosmique ! 450 jours gelés pour 2000% de retour total.', 450, 20.0, 20, 50000)
    ''')

    # Insert top 10 projects - Starting from 20 USDT
    cursor.execute('''
        INSERT OR IGNORE INTO projects (title, description, category, target_amount, expected_return, duration_months, min_investment, max_investment, deadline)
        VALUES 
        ('Crypto Mining Farm', '⛏️ Ferme de minage crypto moderne ! 15% de retour en 6 mois.', 'Mining', 10000, 0.15, 6, 20, 1000, datetime("now", "+30 days")),
        ('E-commerce Platform', '🛒 Plateforme e-commerce innovante ! 18% de retour en 8 mois.', 'Tech', 15000, 0.18, 8, 20, 1500, datetime("now", "+45 days")),
        ('Green Energy Solar', '☀️ Énergie solaire verte ! 20% de retour en 12 mois.', 'Énergie', 25000, 0.20, 12, 20, 2500, datetime("now", "+60 days")),
        ('FinTech Startup', '💳 Startup fintech prometteuse ! 22% de retour en 10 mois.', 'Finance', 20000, 0.22, 10, 20, 2000, datetime("now", "+40 days")),
        ('Real Estate Fund', '🏠 Fonds immobilier diversifié ! 25% de retour en 18 mois.', 'Immobilier', 50000, 0.25, 18, 20, 5000, datetime("now", "+75 days")),
        ('AI Tech Company', '🤖 Entreprise tech IA ! 28% de retour en 14 mois.', 'Intelligence Artificielle', 35000, 0.28, 14, 20, 3500, datetime("now", "+50 days")),
        ('Renewable Energy', '🌱 Énergies renouvelables ! 30% de retour en 20 mois.', 'Écologie', 40000, 0.30, 20, 4000, datetime("now", "+65 days")),
        ('Biotech Innovation', '🧬 Innovation biotechnologique ! 35% de retour en 24 mois.', 'Biotechnologie', 60000, 0.35, 24, 20, 6000, datetime("now", "+80 days")),
        ('Space Technology', '🚀 Technologie spatiale ! 40% de retour en 30 mois.', 'Espace', 80000, 0.40, 30, 20, 8000, datetime("now", "+90 days")),
        ('Quantum Computing', '⚛️ Informatique quantique ! 50% de retour en 36 mois.', 'Quantique', 100000, 0.50, 36, 20, 10000, datetime("now", "+120 days"))
    ''')

    conn.commit()
    conn.close()

# Point d'entrée principal
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestionnaire d'erreur global pour le bot"""
    logger.error("Exception while handling an update:", exc_info=context.error)

    error_message = "❌ Une erreur s'est produite. Veuillez réessayer plus tard."

    # Gérer spécifiquement l'erreur de message trop long
    if "Message_too_long" in str(context.error):
        error_message = "❌ Message trop long. Utilisez /start pour revenir au menu."

    if update:
        try:
            if update.callback_query:
                await update.callback_query.answer()
                await update.callback_query.edit_message_text(error_message)
            elif update.effective_message:
                await update.effective_message.reply_text(error_message)
        except Exception as e:
            logger.error(f"Erreur dans le gestionnaire d'erreur: {e}")
            # En dernier recours, essayer d'envoyer un message simple
            try:
                if update.effective_chat:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text="❌ Erreur système. Tapez /start"
                    )
            except:
                pass

async def start_user_bot():
    """Démarre le bot utilisateur"""
    if not TELEGRAM_BOT_TOKEN:
        print("❌ Impossible de démarrer le bot - Token manquant")
        return False

    app = setup_user_telegram_bot()
    if not app:
        print("❌ Échec de la configuration du bot utilisateur")
        return False

    # Ajouter le gestionnaire d'erreur
    app.add_error_handler(error_handler)

    try:
        print("🚀 Démarrage du bot utilisateur Telegram...")
        await app.initialize()
        await app.start()
        await app.updater.start_polling(
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=True
        )
        print("✅ Bot utilisateur Telegram démarré avec succès!")

        # Initialiser la base de données
        init_db()

        # Utiliser asyncio pour maintenir le bot en vie
        import asyncio

        # Créer un event pour maintenir le bot en vie
        stop_event = asyncio.Event()

        # Fonction pour capturer les signaux d'arrêt
        def signal_handler(signum, frame):
            stop_event.set()

        import signal
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Attendre indéfiniment ou jusqu'à interruption
        try:
            await stop_event.wait()
        except (KeyboardInterrupt, SystemExit):
            stop_event.set()

        return True
    except Exception as e:
        logger.error(f"❌ Erreur bot utilisateur: {e}")
        print(f"❌ Erreur bot utilisateur: {e}")
        return False
    finally:
        try:
            await app.updater.stop()
            await app.stop()
            print("🛑 Bot utilisateur arrêté")
        except:
            pass

if __name__ == "__main__":
    try:
        asyncio.run(start_user_bot())
    except KeyboardInterrupt:
        print("\n🛑 Arrêt du bot par l'utilisateur")
    except Exception as e:
        print(f"❌ Erreur fatale: {e}")