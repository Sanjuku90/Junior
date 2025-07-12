from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
from datetime import datetime, timedelta
import hashlib
import secrets
import json
from functools import wraps
import threading
import time
import sqlite3
from apscheduler.schedulers.background import BackgroundScheduler
import atexit

# Import du bot Telegram utilisateur uniquement
TELEGRAM_ENABLED = False
TELEGRAM_USER_BOT_ENABLED = False


app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

# Configuration
DATABASE = 'investment_platform.db'
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Database initialization
def init_db():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            wallet_address TEXT,
            balance REAL DEFAULT 0.0,
            pending_balance REAL DEFAULT 0.0,
            kyc_status TEXT DEFAULT 'pending',
            referral_code TEXT UNIQUE,
            referred_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            two_fa_enabled BOOLEAN DEFAULT 0,
            two_fa_secret TEXT,
            telegram_id INTEGER UNIQUE,
            last_login TIMESTAMP,
            failed_login_attempts INTEGER DEFAULT 0,
            account_locked BOOLEAN DEFAULT 0,
            locked_until TIMESTAMP
        )
    ''')

    # ROI Plans table
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

    # User Investments table
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

    # Crowdfunding Projects table
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
            image_url TEXT,
            video_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deadline TIMESTAMP
        )
    ''')

    # Project Investments table
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

    # Transactions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            amount REAL NOT NULL,
            status TEXT DEFAULT 'pending',
            transaction_hash TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # Add missing columns to existing tables
    try:
        # Vérifier et ajouter les colonnes manquantes à transactions
        columns = cursor.execute("PRAGMA table_info(transactions)").fetchall()
        column_names = [column[1] for column in columns]
        
        if 'updated_at' not in column_names:
            # Ajouter la colonne sans valeur par défaut d'abord
            cursor.execute('ALTER TABLE transactions ADD COLUMN updated_at TIMESTAMP')
            # Puis mettre à jour les enregistrements existants avec la date actuelle
            cursor.execute('UPDATE transactions SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL')
            print("✅ Colonne updated_at ajoutée à la table transactions")
    except sqlite3.OperationalError as e:
        print(f"⚠️ Erreur ajout colonne updated_at: {e}")

    # Vérifier et ajouter les colonnes 2FA manquantes à users
    try:
        users_columns = cursor.execute("PRAGMA table_info(users)").fetchall()
        users_column_names = [column[1] for column in users_columns]
        
        if 'two_fa_enabled' not in users_column_names:
            cursor.execute('ALTER TABLE users ADD COLUMN two_fa_enabled BOOLEAN DEFAULT 0')
            print("✅ Colonne two_fa_enabled ajoutée à la table users")
            
        if 'two_fa_secret' not in users_column_names:
            cursor.execute('ALTER TABLE users ADD COLUMN two_fa_secret TEXT')
            print("✅ Colonne two_fa_secret ajoutée à la table users")
            
    except sqlite3.OperationalError as e:
        print(f"⚠️ Erreur ajout colonnes 2FA: {e}")

    # Notifications table
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

    # Staking Plans table
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

    # User Staking table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_staking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            plan_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            start_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            end_date TIMESTAMP,
            is_active BOOLEAN DEFAULT 1,
            is_withdrawn BOOLEAN DEFAULT 0,
            total_earned REAL DEFAULT 0.0,
            transaction_hash TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (plan_id) REFERENCES staking_plans (id)
        )
    ''')

    # Frozen Investment Plans table
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

    # User Frozen Investments table
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
            is_completed BOOLEAN DEFAULT 0,
            transaction_hash TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (plan_id) REFERENCES frozen_plans (id)
        )
    ''')

    # Portfolio Distribution table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS portfolio_distributions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            total_amount REAL NOT NULL,
            distribution_data TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # Support Tickets table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS support_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            status TEXT DEFAULT 'open',
            priority TEXT DEFAULT 'normal',
            category TEXT DEFAULT 'general',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            assigned_to TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # Support Messages table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS support_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            user_id INTEGER,
            message TEXT NOT NULL,
            is_admin BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (ticket_id) REFERENCES support_tickets (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # FAQ table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS faq (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Security Logs table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS security_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            details TEXT,
            ip_address TEXT,
            user_agent TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # Insert default FAQ entries
    cursor.execute('''
        INSERT OR IGNORE INTO faq (question, answer, category) VALUES 
        ('Comment déposer des fonds ?', 'Rendez-vous dans votre portefeuille et cliquez sur "Déposer". Suivez les instructions pour transférer vos USDT.', 'wallet'),
        ('Quand puis-je retirer mes gains ?', 'Vos gains quotidiens sont disponibles immédiatement pour retrait. Le capital initial est libéré à la fin du plan.', 'investment'),
        ('Les investissements sont-ils sécurisés ?', 'Oui, nous utilisons des smart contracts et un système de sécurité multicouche pour protéger vos investissements.', 'security'),
        ('Comment fonctionne le parrainage ?', 'Partagez votre code de parrainage unique et recevez 5% sur tous les investissements de vos filleuls.', 'referral'),
        ('Quel est le montant minimum d investissement ?', 'Le montant minimum est de 20 USDT pour tous nos plans d investissement.', 'investment')
    ''')

    # Clear existing plans first to avoid duplicates
    cursor.execute('DELETE FROM roi_plans')
    
    # Insert clean ROI plans - ALL starting from 20 USDT minimum
    cursor.execute('''
        INSERT INTO roi_plans (name, description, daily_rate, duration_days, min_amount, max_amount)
        VALUES 
        ('Starter Pro', '🚀 Parfait pour débuter ! 3% quotidien sur 30 jours. Idéal pour tester nos services avec un petit budget.', 0.03, 30, 20, 500),
        ('Rapid Growth', '⚡ Croissance rapide ! 4% par jour pendant 25 jours. Parfait équilibre temps/profit.', 0.04, 25, 20, 800),
        ('Silver Plan', '🥈 Plan argent ! 5% quotidien sur 30 jours. Notre bestseller pour débutants.', 0.05, 30, 20, 1000),
        ('Golden Boost', '🥇 Plan or ! 8% par jour pendant 35 jours. Excellent retour sur investissement.', 0.08, 35, 20, 2000),
        ('Platinum Elite', '💎 Elite platinum ! 12% quotidien sur 40 jours. Pour investisseurs sérieux.', 0.12, 40, 20, 5000),
        ('Diamond Pro', '💍 Diamant professionnel ! 15% par jour pendant 50 jours. Rendement exceptionnel.', 0.15, 50, 20, 10000),
        ('VIP Supreme', '👑 VIP suprême ! 18% quotidien sur 60 jours. Pour les grands investisseurs.', 0.18, 60, 20, 25000),
        ('Turbo Flash', '⚡ EXCLUSIF ! 20% par jour sur 14 jours ! Trading haute fréquence + arbitrage premium. Réservé aux VIP.', 0.20, 14, 20, 25000),
        ('Lightning Pro', '⚡ FLASH ! 22% par jour sur 10 jours ! Technologie quantum trading + IA prédictive avancée.', 0.22, 10, 20, 30000),
        ('Super Express', '🔥 NOUVEAU ! 25% quotidien pendant 7 jours ! Profits explosifs garantis ! IA révolutionnaire + algorithmes secrets.', 0.25, 7, 20, 10000),
        ('Mega Booster', '💥 LIMITE ! 30% quotidien pendant 5 jours ! Stratégie secrète révolutionnaire ! Places limitées !', 0.30, 5, 20, 15000),
        ('Rocket Launch', '🚀 METEORE ! 35% quotidien pendant 3 jours ! Stratégie ultra-secrète ! Rendement historique jamais vu !', 0.35, 3, 20, 20000)
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
        ('Renewable Energy', '🌱 Énergies renouvelables ! 30% de retour en 20 mois.', 'Écologie', 40000, 0.30, 20, 20, 4000, datetime("now", "+65 days")),
        ('Biotech Innovation', '🧬 Innovation biotechnologique ! 35% de retour en 24 mois.', 'Biotechnologie', 60000, 0.35, 24, 20, 6000, datetime("now", "+80 days")),
        ('Space Technology', '🚀 Technologie spatiale ! 40% de retour en 30 mois.', 'Espace', 80000, 0.40, 30, 20, 8000, datetime("now", "+90 days")),
        ('Quantum Computing', '⚛️ Informatique quantique ! 50% de retour en 36 mois.', 'Quantique', 100000, 0.50, 36, 20, 10000, datetime("now", "+120 days"))
    ''')

    conn.commit()
    conn.close()

# État global pour l'activation admin
ADMIN_ACCESS_ENABLED = False
ADMIN_ACCESS_EXPIRY = None

# Authentication decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Admin decorator avec vérification d'activation
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        global ADMIN_ACCESS_ENABLED, ADMIN_ACCESS_EXPIRY

        # Vérifier si l'accès admin est expiré
        if ADMIN_ACCESS_EXPIRY and datetime.now() > ADMIN_ACCESS_EXPIRY:
            ADMIN_ACCESS_ENABLED = False
            ADMIN_ACCESS_EXPIRY = None

        if 'user_id' not in session or session.get('is_admin') != True:
            flash('Accès refusé. Privilèges administrateur requis.', 'error')
            return redirect(url_for('dashboard'))

        if not ADMIN_ACCESS_ENABLED:
            flash('Accès administrateur désactivé. Activez d\'abord l\'accès avec la commande appropriée.', 'warning')
            return redirect(url_for('admin_activation_required'))

        return f(*args, **kwargs)
    return decorated_function

def enable_admin_access(duration_minutes=30):
    """Active l'accès admin pour une durée limitée"""
    global ADMIN_ACCESS_ENABLED, ADMIN_ACCESS_EXPIRY
    ADMIN_ACCESS_ENABLED = True
    ADMIN_ACCESS_EXPIRY = datetime.now() + timedelta(minutes=duration_minutes)
    print(f"🔓 Accès admin activé pour {duration_minutes} minutes jusqu'à {ADMIN_ACCESS_EXPIRY.strftime('%H:%M:%S')}")

def disable_admin_access():
    """Désactive immédiatement l'accès admin"""
    global ADMIN_ACCESS_ENABLED, ADMIN_ACCESS_EXPIRY
    ADMIN_ACCESS_ENABLED = False
    ADMIN_ACCESS_EXPIRY = None
    print("🔒 Accès admin désactivé")

def get_admin_status():
    """Retourne le statut de l'accès admin"""
    global ADMIN_ACCESS_ENABLED, ADMIN_ACCESS_EXPIRY

    if ADMIN_ACCESS_EXPIRY and datetime.now() > ADMIN_ACCESS_EXPIRY:
        ADMIN_ACCESS_ENABLED = False
        ADMIN_ACCESS_EXPIRY = None

    return {
        'enabled': ADMIN_ACCESS_ENABLED,
        'expiry': ADMIN_ACCESS_EXPIRY,
        'remaining_minutes': (ADMIN_ACCESS_EXPIRY - datetime.now()).total_seconds() / 60 if ADMIN_ACCESS_EXPIRY else 0
    }

# Utility functions
def get_db_connection():
    import time
    max_retries = 5
    for attempt in range(max_retries):
        try:
            conn = sqlite3.connect(DATABASE, timeout=60.0)
            conn.row_factory = sqlite3.Row
            # Enable WAL mode for better concurrency
            conn.execute('PRAGMA journal_mode=WAL;')
            conn.execute('PRAGMA busy_timeout=60000;')  # 60 seconds timeout
            conn.execute('PRAGMA synchronous=NORMAL;')  # Better performance
            conn.execute('PRAGMA cache_size=10000;')     # Larger cache
            conn.execute('PRAGMA temp_store=memory;')    # Use memory for temp
            return conn
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and attempt < max_retries - 1:
                time.sleep(0.5 * (attempt + 1))  # Progressive backoff
                continue
            else:
                print(f"❌ Database connection failed after {max_retries} attempts: {e}")
                raise e
        except Exception as e:
            print(f"❌ Unexpected database error: {e}")
            raise e
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

# Scheduled tasks
def calculate_daily_profits():
    conn = get_db_connection()
    
    # Récupérer tous les investissements actifs
    active_investments = conn.execute('''
        SELECT ui.*, u.email, rp.name as plan_name
        FROM user_investments ui
        JOIN users u ON ui.user_id = u.id
        JOIN roi_plans rp ON ui.plan_id = rp.id
        WHERE ui.is_active = 1
    ''').fetchall()

    print(f"🔄 Calcul des profits pour {len(active_investments)} investissements actifs")

    for investment in active_investments:
        try:
            # Vérifier si l'investissement est vraiment actif (pas expiré)
            from datetime import datetime
            if investment['end_date']:
                end_date = datetime.fromisoformat(investment['end_date'].replace('Z', ''))
                if datetime.now() > end_date:
                    # Marquer comme terminé
                    conn.execute('''
                        UPDATE user_investments 
                        SET is_active = 0 
                        WHERE id = ?
                    ''', (investment['id'],))
                    
                    add_notification(
                        investment['user_id'],
                        'Plan d\'investissement terminé',
                        f'Votre plan {investment["plan_name"]} est arrivé à terme. Total gagné: {investment["total_earned"]:.2f} USDT',
                        'info'
                    )
                    continue

            # Calculate daily profit
            daily_profit = investment['daily_profit']
            
            if daily_profit > 0:
                print(f"💰 Ajout de {daily_profit:.2f} USDT pour l'utilisateur {investment['user_id']} - Plan: {investment['plan_name']}")

                # Update user balance
                conn.execute('''
                    UPDATE users 
                    SET balance = balance + ? 
                    WHERE id = ?
                ''', (daily_profit, investment['user_id']))

                # Update total earned
                current_earned = investment.get('total_earned', 0) or 0
                new_total_earned = current_earned + daily_profit
                conn.execute('''
                    UPDATE user_investments 
                    SET total_earned = ? 
                    WHERE id = ?
                ''', (new_total_earned, investment['id']))

                # Add transaction record
                conn.execute('''
                    INSERT INTO transactions (user_id, type, amount, status, transaction_hash)
                    VALUES (?, 'daily_profit', ?, 'completed', ?)
                ''', (investment['user_id'], daily_profit, generate_transaction_hash()))

                # Add notification
                add_notification(
                    investment['user_id'],
                    'Profit journalier reçu',
                    f'Vous avez reçu {daily_profit:.2f} USDT de votre plan {investment["plan_name"]}',
                    'success'
                )

        except Exception as e:
            print(f"❌ Erreur calcul profit pour investissement {investment['id']}: {e}")
            continue

    conn.commit()
    conn.close()
    print("✅ Calcul des profits quotidiens terminé")

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form

        email = data.get('email')
        password = data.get('password')
        first_name = data.get('first_name')
        last_name = data.get('last_name')
        referral_code = data.get('referral_code', '')

        if not all([email, password, first_name, last_name]):
            return jsonify({'error': 'Tous les champs sont requis'}), 400

        conn = get_db_connection()

        # Check if user already exists
        if conn.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone():
            return jsonify({'error': 'Cet email est déjà utilisé'}), 400

        # Hash password
        password_hash = generate_password_hash(password)
        user_referral_code = generate_referral_code()

        # Insert user
        cursor = conn.execute('''
            INSERT INTO users (email, password_hash, first_name, last_name, referral_code, referred_by)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (email, password_hash, first_name, last_name, user_referral_code, referral_code))

        user_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Auto login
        session['user_id'] = user_id
        session['email'] = email
        session['first_name'] = first_name

        return jsonify({'success': True, 'redirect': url_for('dashboard')})

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form

        email = data.get('email')
        password = data.get('password')

        if not email or not password:
            return jsonify({'error': 'Email et mot de passe requis'}), 400

        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        conn.close()

        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['email'] = user['email']
            session['first_name'] = user['first_name']

            # Liste blanche des administrateurs autorisés - TOUS LES UTILISATEURS
            ADMIN_EMAILS = [
                'admin@investcryptopro.com',
                'support@investcryptopro.com',
                'security@investcryptopro.com',
                'a@gmail.com'
            ]

            # Vérification admin sécurisée - ACCÈS POUR TOUS LES UTILISATEURS
            # Tous les utilisateurs peuvent maintenant accéder à l'admin après activation
            is_potential_admin = True  # Tous les utilisateurs peuvent être admin
            session['is_admin'] = False  # Toujours False par défaut
            session['is_potential_admin'] = is_potential_admin

            # Log de connexion admin potentiel
            if is_potential_admin:
                log_security_action(user['id'], 'potential_admin_login', f'Connexion utilisateur avec privilèges admin potentiels depuis {request.remote_addr}')

            return jsonify({'success': True, 'redirect': url_for('dashboard')})

        return jsonify({'error': 'Email ou mot de passe incorrect'}), 401

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db_connection()

    # Get user info
    user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()

    # Get active investments
    investments = conn.execute('''
        SELECT ui.*, rp.name as plan_name, rp.daily_rate
        FROM user_investments ui
        JOIN roi_plans rp ON ui.plan_id = rp.id
        WHERE ui.user_id = ? AND ui.is_active = 1 AND (ui.end_date > datetime('now') OR ui.end_date IS NULL)
        ORDER BY ui.start_date DESC
    ''', (session['user_id'],)).fetchall()

    # Get project investments
    project_investments = conn.execute('''
        SELECT pi.*, p.title, p.status, p.expected_return
        FROM project_investments pi
        JOIN projects p ON pi.project_id = p.id
        WHERE pi.user_id = ?
        ORDER BY pi.investment_date DESC
    ''', (session['user_id'],)).fetchall()

    # Get notifications
    notifications_raw = conn.execute('''
        SELECT * FROM notifications 
        WHERE user_id = ? AND is_read = 0
        ORDER BY created_at DESC
        LIMIT 5
    ''', (session['user_id'],)).fetchall()

    # Convert notifications to dict and parse datetime safely
    notifications = []
    for notif in notifications_raw:
        notif_dict = dict(notif)
        try:
            if notif_dict.get('created_at'):
                if isinstance(notif_dict['created_at'], str):
                    # Remove timezone suffix if present and parse
                    date_str = notif_dict['created_at'].replace('Z', '').replace('+00:00', '')
                    notif_dict['created_at'] = datetime.fromisoformat(date_str)
                elif hasattr(notif_dict['created_at'], 'strftime'):
                    # Already a datetime object
                    pass
                else:
                    notif_dict['created_at'] = datetime.now()
            else:
                notif_dict['created_at'] = datetime.now()
        except Exception as e:
            print(f"⚠️ Erreur parsing date notification: {e}")
            notif_dict['created_at'] = datetime.now()
        notifications.append(notif_dict)

    conn.close()

    # Debug info
    print(f"DEBUG: User {session['user_id']} has {len(investments)} active investments")
    for inv in investments:
        print(f"DEBUG: Investment {inv['id']}: {inv['plan_name']}, amount: {inv['amount']}, active: {inv['is_active']}")

    return render_template('dashboard.html', 
                         user=user, 
                         investments=investments, 
                         project_investments=project_investments,
                         notifications=notifications)



@app.route('/roi-plans')
@login_required
def roi_plans():
    """Page des plans d'investissement ROI"""
    conn = get_db_connection()
    
    # Récupérer tous les plans ROI actifs
    plans = conn.execute('''
        SELECT * FROM roi_plans 
        WHERE is_active = 1
        ORDER BY daily_rate ASC, duration_days ASC
    ''').fetchall()
    
    conn.close()

    return render_template('roi_plans.html', plans=plans)

@app.route('/ultra-plans')
@login_required
def ultra_plans():
    """Page dédiée aux plans ultra-rentables (20%+ quotidien)"""
    conn = get_db_connection()
    
    # Récupérer seulement les plans ultra-rentables (20%+ quotidien)
    ultra_plans = conn.execute('''
        SELECT * FROM roi_plans 
        WHERE is_active = 1 AND daily_rate >= 0.20
        ORDER BY daily_rate DESC, duration_days ASC
    ''').fetchall()
    
    conn.close()

    return render_template('ultra_plans.html', ultra_plans=ultra_plans)



@app.route('/projects')
@login_required
def projects():
    conn = get_db_connection()
    projects = conn.execute('''
        SELECT *, 
               (raised_amount * 100.0 / target_amount) as progress_percent
        FROM projects 
        WHERE status = 'collecting' AND deadline > datetime('now')
        ORDER BY created_at DESC
    ''').fetchall()
    conn.close()

    return render_template('projects.html', projects=projects)

@app.route('/project/<int:project_id>')
@login_required
def project_detail(project_id):
    conn = get_db_connection()
    project = conn.execute('''
        SELECT *, 
               (raised_amount * 100.0 / target_amount) as progress_percent
        FROM projects 
        WHERE id = ?
    ''', (project_id,)).fetchone()

    if not project:
        flash('Projet non trouvé', 'error')
        return redirect(url_for('projects'))

    # Get project investments
    investments = conn.execute('''
        SELECT pi.*, u.first_name, u.last_name
        FROM project_investments pi
        JOIN users u ON pi.user_id = u.id
        WHERE pi.project_id = ?
        ORDER BY pi.investment_date DESC
    ''', (project_id,)).fetchall()

    conn.close()

    return render_template('project_detail.html', project=project, investments=investments)

@app.route('/invest-roi', methods=['POST'])
@login_required
def invest_roi():
    """Investir dans un plan ROI"""
    data = request.get_json()
    plan_id = data.get('plan_id')
    amount = float(data.get('amount', 0))

    conn = get_db_connection()

    # Get plan details
    plan = conn.execute('SELECT * FROM roi_plans WHERE id = ?', (plan_id,)).fetchone()
    if not plan:
        return jsonify({'error': 'Plan ROI non trouvé'}), 404

    # Check amount limits
    if amount < plan['min_amount'] or amount > plan['max_amount']:
        return jsonify({'error': f'Montant doit être entre {plan["min_amount"]} et {plan["max_amount"]} USDT'}), 400

    # Check user balance
    user = conn.execute('SELECT balance FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    if user['balance'] < amount:
        return jsonify({'error': 'Solde insuffisant'}), 400

    # Calculate dates and daily profit
    start_date = datetime.now()
    end_date = start_date + timedelta(days=plan['duration_days'])
    daily_profit = amount * plan['daily_rate']

    # Create investment
    conn.execute('''
        INSERT INTO user_investments (user_id, plan_id, amount, start_date, end_date, daily_profit, transaction_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (session['user_id'], plan_id, amount, start_date, end_date, daily_profit, generate_transaction_hash()))

    # Update user balance
    conn.execute('UPDATE users SET balance = balance - ? WHERE id = ?', (amount, session['user_id']))

    # Add transaction record
    conn.execute('''
        INSERT INTO transactions (user_id, type, amount, status, transaction_hash)
        VALUES (?, 'roi_investment', ?, 'completed', ?)
    ''', (session['user_id'], amount, generate_transaction_hash()))

    conn.commit()
    conn.close()

    # Add notification
    add_notification(
        session['user_id'],
        'Investissement ROI créé',
        f'Votre investissement de {amount} USDT dans le plan {plan["name"]} a été créé avec succès!',
        'success'
    )

    return jsonify({'success': True, 'message': f'Investissement de {amount} USDT créé avec succès!'})

@app.route('/invest-project', methods=['POST'])
@login_required
def invest_project():
    data = request.get_json()
    project_id = data.get('project_id')
    amount = float(data.get('amount', 0))

    conn = get_db_connection()

    # Get project details
    project = conn.execute('SELECT * FROM projects WHERE id = ?', (project_id,)).fetchone()
    if not project:
        return jsonify({'error': 'Projet non trouvé'}), 404

    # Check amount limits
    if amount < project['min_investment'] or amount > project['max_investment']:
        return jsonify({'error': f'Montant doit être entre {project["min_investment"]} et {project["max_investment"]} USDT'}), 400

    # Check user balance
    user = conn.execute('SELECT balance FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    if user['balance'] < amount:
        return jsonify({'error': 'Solde insuffisant'}), 400

    # Create investment
    conn.execute('''
        INSERT INTO project_investments (user_id, project_id, amount, transaction_hash)
        VALUES (?, ?, ?, ?)
    ''', (session['user_id'], project_id, amount, generate_transaction_hash()))

    # Update user balance and project raised amount
    conn.execute('UPDATE users SET balance = balance - ? WHERE id = ?', (amount, session['user_id']))
    conn.execute('UPDATE projects SET raised_amount = raised_amount + ? WHERE id = ?', (amount, project_id))

    # Add transaction record
    conn.execute('''
        INSERT INTO transactions (user_id, type, amount, status, transaction_hash)
        VALUES (?, 'project_investment', ?, 'completed', ?)
    ''', (session['user_id'], amount, generate_transaction_hash()))

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'Investissement dans le projet réalisé avec succès!'})

@app.route('/profile')
@login_required
def profile():
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()

    # Get referral stats
    referrals = conn.execute('''
        SELECT COUNT(*) as count, COALESCE(SUM(balance), 0) as total_balance
        FROM users 
        WHERE referred_by = ?
    ''', (user['referral_code'],)).fetchone()

    # Get user balance for navbar
    user_balance = user['balance'] if user['balance'] else 0.0

    conn.close()

    return render_template('profile.html', user=user, referrals=referrals, user_balance=user_balance)

@app.route('/staking-plans')
@login_required
def staking_plans():
    conn = get_db_connection()
    plans = conn.execute('SELECT * FROM staking_plans WHERE is_active = 1').fetchall()
    conn.close()

    return render_template('staking_plans.html', plans=plans)

@app.route('/invest-staking', methods=['POST'])
@login_required
def invest_staking():
    data = request.get_json()
    plan_id = data.get('plan_id')
    amount = float(data.get('amount', 0))

    conn = get_db_connection()

    # Get plan details
    plan = conn.execute('SELECT * FROM staking_plans WHERE id = ?', (plan_id,)).fetchone()
    if not plan:
        return jsonify({'error': 'Plan de staking non trouvé'}), 404

    # Check amount limits
    if amount < plan['min_amount'] or amount > plan['max_amount']:
        return jsonify({'error': f'Montant doit être entre {plan["min_amount"]} et {plan["max_amount"]} USDT'}), 400

    # Check user balance
    user = conn.execute('SELECT balance FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    if user['balance'] < amount:
        return jsonify({'error': 'Solde insuffisant'}), 400

    # Calculate dates
    start_date = datetime.now()
    end_date = start_date + timedelta(days=plan['duration_days'])

    # Create staking
    conn.execute('''
        INSERT INTO user_staking (user_id, plan_id, amount, start_date, end_date, transaction_hash)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (session['user_id'], plan_id, amount, start_date, end_date, generate_transaction_hash()))

    # Update user balance
    conn.execute('UPDATE users SET balance = balance - ? WHERE id = ?', (amount, session['user_id']))

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'Staking activé avec succès!'})

@app.route('/frozen-plans')
@login_required
def frozen_plans():
    conn = get_db_connection()
    plans = conn.execute('SELECT * FROM frozen_plans WHERE is_active = 1').fetchall()
    conn.close()

    return render_template('frozen_plans.html', plans=plans)

@app.route('/invest-frozen', methods=['POST'])
@login_required
def invest_frozen():
    data = request.get_json()
    plan_id = data.get('plan_id')
    amount = float(data.get('amount', 0))

    conn = get_db_connection()

    # Get plan details
    plan = conn.execute('SELECT * FROM frozen_plans WHERE id = ?', (plan_id,)).fetchone()
    if not plan:
        return jsonify({'error': 'Plan gelé non trouvé'}), 404

    # Check amount limits
    if amount < plan['min_amount'] or amount > plan['max_amount']:
        return jsonify({'error': f'Montant doit être entre {plan["min_amount"]} et {plan["max_amount"]} USDT'}), 400

    # Check user balance
    user = conn.execute('SELECT balance FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    if user['balance'] < amount:
        return jsonify({'error': 'Solde insuffisant'}), 400

    # Calculate dates and final amount
    start_date = datetime.now()
    end_date = start_date + timedelta(days=plan['duration_days'])
    final_amount = amount * plan['total_return_rate']

    # Create frozen investment
    conn.execute('''
        INSERT INTO user_frozen_investments (user_id, plan_id, amount, start_date, end_date, final_amount, transaction_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (session['user_id'], plan_id, amount, start_date, end_date, final_amount, generate_transaction_hash()))

    # Update user balance
    conn.execute('UPDATE users SET balance = balance - ? WHERE id = ?', (amount, session['user_id']))

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'Investissement gelé créé avec succès!'})

@app.route('/portfolio-invest', methods=['POST'])
@login_required
def portfolio_invest():
    data = request.get_json()
    total_amount = float(data.get('total_amount', 0))
    distributions = data.get('distributions', [])

    if not distributions or total_amount <= 0:
        return jsonify({'error': 'Données de répartition invalides'}), 400

    conn = get_db_connection()

    # Check user balance
    user = conn.execute('SELECT balance FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    if user['balance'] < total_amount:
        return jsonify({'error': 'Solde insuffisant'}), 400

    # Process each distribution
    for dist in distributions:
        investment_type = dist.get('type')
        plan_id = dist.get('plan_id')
        amount = float(dist.get('amount', 0))

        if investment_type == 'roi':
            plan = conn.execute('SELECT * FROM roi_plans WHERE id = ?', (plan_id,)).fetchone()
            if plan:
                start_date = datetime.now()
                end_date = start_date + timedelta(days=plan['duration_days'])
                daily_profit = amount * plan['daily_rate']

                conn.execute('''
                    INSERT INTO user_investments (user_id, plan_id, amount, start_date, end_date, daily_profit, transaction_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (session['user_id'], plan_id, amount, start_date, end_date, daily_profit, generate_transaction_hash()))

        elif investment_type == 'staking':
            plan = conn.execute('SELECT * FROM staking_plans WHERE id = ?', (plan_id,)).fetchone()
            if plan:
                start_date = datetime.now()
                end_date = start_date + timedelta(days=plan['duration_days'])

                conn.execute('''
                    INSERT INTO user_staking (user_id, plan_id, amount, start_date, end_date, transaction_hash)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (session['user_id'], plan_id, amount, start_date, end_date, generate_transaction_hash()))

        elif investment_type == 'project':
            conn.execute('''
                INSERT INTO project_investments (user_id, project_id, amount, transaction_hash)
                VALUES (?, ?, ?, ?)
            ''', (session['user_id'], plan_id, amount, generate_transaction_hash()))

            conn.execute('UPDATE projects SET raised_amount = raised_amount + ? WHERE id = ?', (amount, plan_id))

    # Save portfolio distribution
    conn.execute('''
        INSERT INTO portfolio_distributions (user_id, total_amount, distribution_data)
        VALUES (?, ?, ?)
    ''', (session['user_id'], total_amount, json.dumps(distributions)))

    # Update user balance
    conn.execute('UPDATE users SET balance = balance - ? WHERE id = ?', (total_amount, session['user_id']))

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'Portfolio diversifié créé avec succès!'})

@app.route('/deposit', methods=['POST'])
@login_required
def submit_deposit():
    """Soumettre une demande de dépôt"""
    data = request.get_json()
    amount = float(data.get('amount', 0))
    transaction_hash = data.get('transaction_hash', '')

    if not amount or not transaction_hash:
        return jsonify({'error': 'Montant et hash de transaction requis'}), 400

    if amount < 10:
        return jsonify({'error': 'Montant minimum de dépôt: 10 USDT'}), 400

    conn = get_db_connection()

    # Créer la transaction en attente
    cursor = conn.execute('''
        INSERT INTO transactions (user_id, type, amount, status, transaction_hash)
        VALUES (?, 'deposit', ?, 'pending', ?)
    ''', (session['user_id'], amount, transaction_hash))

    deposit_id = cursor.lastrowid
    conn.commit()
    conn.close()

    # Notification admin pour nouveau dépôt
    add_notification(
        1,  # ID admin par défaut
        'Nouveau dépôt à vérifier',
        f'Nouvelle demande de dépôt: {amount} USDT de {session.get("email", "Utilisateur")} - Hash: {transaction_hash[:16]}...',
        'info'
    )

    # Ajouter une notification à l'utilisateur
    add_notification(
        session['user_id'],
        'Dépôt en cours de vérification',
        f'Votre dépôt de {amount} USDT est en cours de vérification par notre équipe.',
        'info'
    )

    return jsonify({'success': True, 'message': 'Dépôt soumis pour vérification'})

@app.route('/withdraw', methods=['POST'])
@login_required
def submit_withdrawal():
    """Soumettre une demande de retrait"""
    data = request.get_json()
    amount = float(data.get('amount', 0))
    withdrawal_address = data.get('withdrawal_address', '')

    if not amount or not withdrawal_address:
        return jsonify({'error': 'Montant et adresse de retrait requis'}), 400

    if amount < 10:
        return jsonify({'error': 'Montant minimum de retrait: 10 USDT'}), 400

    conn = get_db_connection()

    # Vérifier le solde utilisateur
    user = conn.execute('SELECT balance FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    if user['balance'] < amount:
        return jsonify({'error': 'Solde insuffisant'}), 400

    # Débiter temporairement le solde
    conn.execute('UPDATE users SET balance = balance - ? WHERE id = ?', (amount, session['user_id']))

    # Créer la transaction en attente
    cursor = conn.execute('''
        INSERT INTO transactions (user_id, type, amount, status, transaction_hash)
        VALUES (?, 'withdrawal', ?, 'pending', ?)
    ''', (session['user_id'], amount, f"withdrawal_{generate_transaction_hash()[:16]}"))

    withdrawal_id = cursor.lastrowid

    # Stocker l'adresse de retrait
    conn.execute('''
        UPDATE transactions 
        SET transaction_hash = ? 
        WHERE id = ?
    ''', (f"{withdrawal_address}|{amount}", withdrawal_id))

    conn.commit()
    conn.close()

    # Notification admin pour nouveau retrait
    add_notification(
        1,  # ID admin par défaut
        'Nouveau retrait à traiter',
        f'Nouvelle demande de retrait: {amount} USDT de {session.get("email", "Utilisateur")} vers {withdrawal_address[:20]}...',
        'info'
    )

    # Ajouter une notification à l'utilisateur
    add_notification(
        session['user_id'],
        'Retrait en cours de traitement',
        f'Votre demande de retrait de {amount} USDT est en cours de traitement.',
        'info'
    )

    return jsonify({'success': True, 'message': 'Demande de retrait soumise pour traitement'})

# Support routes
@app.route('/support')
@login_required
def support():
    conn = get_db_connection()

    # Get user's tickets
    tickets = conn.execute('''
        SELECT st.*, 
               (SELECT COUNT(*) FROM support_messages sm WHERE sm.ticket_id = st.id) as message_count,
               (SELECT sm.created_at FROM support_messages sm WHERE sm.ticket_id = st.id ORDER BY sm.created_at DESC LIMIT 1) as last_message_at
        FROM support_tickets st
        WHERE st.user_id = ?
        ORDER BY st.created_at DESC
    ''', (session['user_id'],)).fetchall()

    # Get FAQ
    faq_items = conn.execute('''
        SELECT * FROM faq WHERE is_active = 1 ORDER BY category, id
    ''').fetchall()

    conn.close()

    return render_template('support.html', tickets=tickets, faq_items=faq_items)

@app.route('/support/ticket/<int:ticket_id>')
@login_required
def support_ticket(ticket_id):
    conn = get_db_connection()

    # Get ticket details
    ticket = conn.execute('''
        SELECT st.*, u.first_name, u.last_name, u.email
        FROM support_tickets st
        JOIN users u ON st.user_id = u.id
        WHERE st.id = ? AND st.user_id = ?
    ''', (ticket_id, session['user_id'])).fetchone()

    if not ticket:
        flash('Ticket non trouvé', 'error')
        return redirect(url_for('support'))

    # Get messages
    messages = conn.execute('''
        SELECT sm.*, u.first_name, u.last_name
        FROM support_messages sm
        LEFT JOIN users u ON sm.user_id = u.id
        WHERE sm.ticket_id = ?
        ORDER BY sm.created_at ASC
    ''', (ticket_id,)).fetchall()

    conn.close()

    return render_template('support_ticket.html', ticket=ticket, messages=messages)

@app.route('/support/create-ticket', methods=['POST'])
@login_required
def create_support_ticket():
    data = request.get_json()
    subject = data.get('subject', '').strip()
    message = data.get('message', '').strip()
    category = data.get('category', 'general')
    priority = data.get('priority', 'normal')

    # Informations supplémentaires optionnelles
    amount = data.get('amount', '')
    tx_hash = data.get('tx_hash', '')

    if not subject or not message:
        return jsonify({'error': 'Sujet et message requis'}), 400

    # Enrichir le message avec les informations supplémentaires
    enriched_message = message
    if amount or tx_hash:
        enriched_message += "\n\n--- Informations supplémentaires ---"
        if amount:
            enriched_message += f"\n💰 Montant concerné: {amount} USDT"
        if tx_hash:
            enriched_message += f"\n🔗 Hash de transaction: {tx_hash}"

    conn = get_db_connection()

    try:
        # Create ticket
        cursor = conn.execute('''
            INSERT INTO support_tickets (user_id, subject, category, priority)
            VALUES (?, ?, ?, ?)
        ''', (session['user_id'], subject, category, priority))

        ticket_id = cursor.lastrowid

        # Add first message
        conn.execute('''
            INSERT INTO support_messages (ticket_id, user_id, message, is_admin)
            VALUES (?, ?, ?, 0)
        ''', (ticket_id, session['user_id'], enriched_message))

        conn.commit()

        # Notification utilisateur
        add_notification(
            session['user_id'],
            'Ticket de support créé',
            f'Votre ticket #{ticket_id} a été créé avec succès. Notre équipe va vous répondre rapidement.',
            'success'
        )

        # Notification admin
        add_notification(
            1,  # Admin user ID
            'Nouveau ticket de support',
            f'Nouveau ticket #{ticket_id} - {category.upper()} - Priorité: {priority}',
            'info'
        )

        # Notifier l'admin via Telegram si disponible


        return jsonify({
            'success': True, 
            'ticket_id': ticket_id,
            'message': f'Ticket #{ticket_id} créé avec succès!'
        })

    except Exception as e:
        conn.rollback()
        print(f"Erreur création ticket: {e}")
        return jsonify({'error': 'Erreur lors de la création du ticket'}), 500
    finally:
        conn.close()

@app.route('/support/send-message', methods=['POST'])
@login_required
def send_support_message():
    data = request.get_json()
    ticket_id = data.get('ticket_id')
    message = data.get('message', '').strip()

    if not message:
        return jsonify({'error': 'Message requis'}), 400

    conn = get_db_connection()

    # Verify ticket belongs to user
    ticket = conn.execute('''
        SELECT id FROM support_tickets 
        WHERE id = ? AND user_id = ?
    ''', (ticket_id, session['user_id'])).fetchone()

    if not ticket:
        return jsonify({'error': 'Ticket non trouvé'}), 404

    # Add message
    conn.execute('''
        INSERT INTO support_messages (ticket_id, user_id, message, is_admin)
        VALUES (?, ?, ?, 0)
    ''', (ticket_id, session['user_id'], message))

    # Update ticket timestamp
    conn.execute('''
        UPDATE support_tickets 
        SET updated_at = CURRENT_TIMESTAMP, status = 'user_reply'
        WHERE id = ?
    ''', (ticket_id,))

    conn.commit()
    conn.close()

    return jsonify({'success': True})

@app.route('/support/get-messages/<int:ticket_id>')
@login_required
def get_support_messages(ticket_id):
    try:
        conn = get_db_connection()

        # Verify ticket belongs to user
        ticket = conn.execute('''
            SELECT id FROM support_tickets 
            WHERE id = ? AND user_id = ?
        ''', (ticket_id, session['user_id'])).fetchone()

        if not ticket:
            conn.close()
            return jsonify({'error': 'Ticket non trouvé'}), 404

        # Get messages
        messages = conn.execute('''
            SELECT sm.*, u.first_name, u.last_name
            FROM support_messages sm
            LEFT JOIN users u ON sm.user_id = u.id
            WHERE sm.ticket_id = ?
            ORDER BY sm.created_at ASC
        ''', (ticket_id,)).fetchall()

        conn.close()

        messages_list = []
        for msg in messages:
            # Gérer les valeurs NULL proprement
            first_name = msg['first_name'] if msg['first_name'] else ''
            last_name = msg['last_name'] if msg['last_name'] else ''

            sender_name = 'Support' if msg['is_admin'] else f"{first_name} {last_name}".strip()
            if not sender_name or sender_name.isspace():
                sender_name = 'Utilisateur'

            messages_list.append({
                'id': msg['id'],
                'message': msg['message'] if msg['message'] else '',
                'is_admin': bool(msg['is_admin']),
                'created_at': msg['created_at'] if msg['created_at'] else '',
                'sender_name': sender_name
            })

        return jsonify({
            'success': True,
            'messages': messages_list,
            'ticket_id': ticket_id
        })

    except Exception as e:
        print(f"Erreur get_support_messages: {e}")
        return jsonify({'error': 'Erreur serveur'}), 500

@app.route('/admin')
def admin_panel():
    """Panneau d'administration principal - ACCÈS LIBRE"""
    # Créer une session temporaire admin si elle n'existe pas
    if 'user_id' not in session:
        session['user_id'] = 1  # ID admin temporaire
        session['email'] = 'admin@temp.local'
        session['first_name'] = 'Admin'
        session['is_potential_admin'] = True
        session['is_admin'] = False

    # Vérifier si l'accès admin est activé
    admin_status = get_admin_status()
    if not admin_status['enabled'] or not session.get('is_admin'):
        return redirect(url_for('admin_activation_required'))

    # Accès admin confirmé - afficher le dashboard admin
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    """Dashboard administrateur avec statistiques"""
    conn = get_db_connection()

    # Statistiques générales
    stats = {}
    stats['total_users'] = conn.execute('SELECT COUNT(*) as count FROM users').fetchone()['count']
    stats['total_investments'] = conn.execute('SELECT COALESCE(SUM(amount), 0) as total FROM user_investments').fetchone()['total']
    stats['total_projects'] = conn.execute('SELECT COUNT(*) as count FROM projects').fetchone()['count']
    stats['pending_kyc'] = conn.execute('SELECT COUNT(*) as count FROM users WHERE kyc_status = "pending"').fetchone()['count']

    # Transactions récentes
    transactions = conn.execute('''
        SELECT t.*, u.first_name, u.last_name, u.email
        FROM transactions t
        JOIN users u ON t.user_id = u.id
        ORDER BY t.created_at DESC
        LIMIT 10
    ''').fetchall()

    # Tickets de support ouverts
    try:
        stats['open_tickets'] = conn.execute('SELECT COUNT(*) as count FROM support_tickets WHERE status != "closed"').fetchone()['count']
    except:
        stats['open_tickets'] = 0

    conn.close()

    return render_template('admin_dashboard.html', stats=stats, transactions=transactions)

@app.route('/admin-activation-required')
def admin_activation_required():
    """Page d'activation admin requis - ACCÈS LIBRE"""
    # Créer une session temporaire admin si elle n'existe pas
    if 'user_id' not in session:
        session['user_id'] = 1  # ID admin temporaire
        session['email'] = 'admin@temp.local'
        session['first_name'] = 'Admin'
        session['is_potential_admin'] = True
        session['is_admin'] = False

    admin_status = get_admin_status()
    return render_template('admin_activation.html', admin_status=admin_status)

@app.route('/admin/activate', methods=['POST'])
def activate_admin_access():
    """Active l'accès admin avec code de sécurité - ACCÈS LIBRE"""
    # Créer une session temporaire admin si elle n'existe pas
    if 'user_id' not in session:
        session['user_id'] = 1  # ID admin temporaire
        session['email'] = 'admin@temp.local'
        session['first_name'] = 'Admin'
        session['is_potential_admin'] = True
        session['is_admin'] = False

    data = request.get_json()
    activation_code = data.get('activation_code')
    duration = int(data.get('duration', 30))  # Durée en minutes

    # Codes d'activation sécurisés (peuvent être changés périodiquement)
    VALID_CODES = [
        'ADMIN2024!',
        'SECURE_ACCESS_' + datetime.now().strftime('%Y%m%d'),
        'EMERGENCY_' + str(datetime.now().hour * 100 + datetime.now().minute)
    ]

    if activation_code not in VALID_CODES:
        log_security_action(session['user_id'], 'admin_activation_failed', f'Code d\'activation invalide: {activation_code}')
        return jsonify({'error': 'Code d\'activation invalide'}), 401

    # Activer l'accès admin
    enable_admin_access(duration)
    session['is_admin'] = True
    session['admin_activated_at'] = datetime.now().isoformat()

    log_security_action(session['user_id'], 'admin_access_activated', f'Accès admin activé pour {duration} minutes')

    return jsonify({
        'success': True, 
        'message': f'Accès admin activé pour {duration} minutes',
        'expiry': ADMIN_ACCESS_EXPIRY.isoformat() if ADMIN_ACCESS_EXPIRY else None
    })

@app.route('/admin/deactivate', methods=['POST'])
def deactivate_admin_access():
    """Désactive immédiatement l'accès admin - ACCÈS LIBRE"""
    # Créer une session temporaire si elle n'existe pas
    if 'user_id' not in session:
        session['user_id'] = 1

    # Permettre la désactivation même si is_admin est False
    # car l'utilisateur peut vouloir désactiver un accès expiré

    disable_admin_access()
    session['is_admin'] = False

    log_security_action(session['user_id'], 'admin_access_deactivated', 'Accès admin désactivé manuellement')

    return jsonify({'success': True, 'message': 'Accès admin désactivé'})

@app.route('/admin/status')
def admin_status():
    """Retourne le statut de l'accès admin - ACCÈS LIBRE"""
    # Créer une session temporaire si elle n'existe pas
    if 'user_id' not in session:
        session['user_id'] = 1
        session['is_potential_admin'] = True
        session['is_admin'] = False

    status = get_admin_status()
    return jsonify({
        'is_potential_admin': session.get('is_potential_admin', True),
        'is_admin_active': session.get('is_admin', False),
        'access_enabled': status['enabled'],
        'expiry': status['expiry'].isoformat() if status['expiry'] else None,
        'remaining_minutes': round(status['remaining_minutes'], 1)
    })

# Commande console pour activer admin (pour les développeurs)
def admin_console_activate(duration=30):
    """Fonction console pour activer l'accès admin"""
    enable_admin_access(duration)
    return f"Accès admin activé pour {duration} minutes"

def admin_console_deactivate():
    """Fonction console pour désactiver l'accès admin"""
    disable_admin_access()
    return "Accès admin désactivé"

def admin_console_status():
    """Fonction console pour voir le statut admin"""
    status = get_admin_status()
    if status['enabled']:
        return f"Admin ACTIVÉ - Expire dans {status['remaining_minutes']:.1f} minutes ({status['expiry']})"
    else:
        return "Admin DÉSACTIVÉ"

def restore_user_investments(user_id, investments_data=None):
    """Restaurer les investissements d'un utilisateur"""
    conn = get_db_connection()
    
    if investments_data is None:
        # Données d'exemple pour restauration d'urgence
        investments_data = [
            {
                'plan_id': 1, 'amount': 100, 'days_remaining': 25,
                'daily_profit': 3.0, 'total_earned': 15.0
            },
            {
                'plan_id': 5, 'amount': 500, 'days_remaining': 35,
                'daily_profit': 60.0, 'total_earned': 150.0
            }
        ]
    
    try:
        for inv_data in investments_data:
            start_date = datetime.now() - timedelta(days=(30 - inv_data.get('days_remaining', 30)))
            end_date = datetime.now() + timedelta(days=inv_data.get('days_remaining', 30))
            
            conn.execute('''
                INSERT INTO user_investments (user_id, plan_id, amount, start_date, end_date, daily_profit, total_earned, is_active, transaction_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
            ''', (
                user_id, 
                inv_data['plan_id'], 
                inv_data['amount'], 
                start_date, 
                end_date, 
                inv_data['daily_profit'], 
                inv_data.get('total_earned', 0),
                generate_transaction_hash()
            ))
        
        conn.commit()
        conn.close()
        
        # Notification
        add_notification(
            user_id,
            'Investissements restaurés',
            f'{len(investments_data)} investissement(s) ont été restaurés avec succès.',
            'success'
        )
        
        print(f"✅ {len(investments_data)} investissements restaurés pour l'utilisateur {user_id}")
        return True
        
    except Exception as e:
        conn.rollback()
        conn.close()
        print(f"❌ Erreur restauration investissements: {e}")
        return False

@app.route('/admin/transactions')
@admin_required
def admin_transactions():
    """Gestion des transactions (dépôts/retraits)"""
    conn = get_db_connection()

    # Récupérer toutes les transactions en attente
    pending_transactions = conn.execute('''
        SELECT t.*, u.first_name, u.last_name, u.email
        FROM transactions t
        JOIN users u ON t.user_id = u.id
        WHERE t.status = 'pending'
        ORDER BY t.created_at DESC
    ''').fetchall()

    conn.close()

    return render_template('admin_transactions.html', transactions=pending_transactions)

@app.route('/admin/approve-transaction/<int:transaction_id>', methods=['POST'])
@admin_required
def approve_transaction(transaction_id):
    """Approuver une transaction"""
    try:
        conn = get_db_connection()
        
        # Récupérer la transaction
        transaction = conn.execute('''
            SELECT t.*, u.email, u.first_name, u.balance
            FROM transactions t
            JOIN users u ON t.user_id = u.id
            WHERE t.id = ? AND t.status = 'pending'
        ''', (transaction_id,)).fetchone()

        if not transaction:
            conn.close()
            return jsonify({'error': 'Transaction non trouvée ou déjà traitée'}), 404

        # Validation des données
        if not transaction['amount'] or transaction['amount'] <= 0:
            conn.close()
            return jsonify({'error': 'Montant de transaction invalide'}), 400

        # Traiter selon le type de transaction
        if transaction['type'] == 'deposit':
            # Approuver le dépôt - créditer le compte
            new_balance = transaction['balance'] + transaction['amount']
            conn.execute('''
                UPDATE users 
                SET balance = ?
                WHERE id = ?
            ''', (new_balance, transaction['user_id']))

            # Message de notification pour dépôt
            notification_msg = f'Votre dépôt de {transaction["amount"]:.2f} USDT a été approuvé et crédité à votre compte. Nouveau solde: {new_balance:.2f} USDT'
            
        elif transaction['type'] == 'withdrawal':
            # Le montant a déjà été débité lors de la demande
            # Message de notification pour retrait
            notification_msg = f'Votre retrait de {transaction["amount"]:.2f} USDT a été traité avec succès et sera envoyé à votre adresse.'
            
        else:
            conn.close()
            return jsonify({'error': 'Type de transaction non supporté'}), 400

        # Marquer la transaction comme complétée avec updated_at
        conn.execute('''
            UPDATE transactions 
            SET status = 'completed', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (transaction_id,))

        # Valider toutes les modifications
        conn.commit()
        conn.close()

        # Ajouter notification après fermeture de la connexion
        add_notification(
            transaction['user_id'],
            f'{transaction["type"].title()} approuvé ✅',
            notification_msg,
            'success'
        )

        # Log de sécurité
        log_security_action(
            session.get('user_id', 1), 
            f'{transaction["type"]}_approved', 
            f'{transaction["type"].title()} #{transaction_id} approuvé: {transaction["amount"]} USDT pour {transaction["email"]}'
        )

        print(f"✅ Transaction #{transaction_id} ({transaction['type']}) approuvée avec succès")
        
        return jsonify({
            'success': True, 
            'message': f'{transaction["type"].title()} #{transaction_id} approuvé avec succès'
        })

    except Exception as e:
        print(f"❌ Erreur lors de l'approbation: {e}")
        if 'conn' in locals():
            try:
                conn.rollback()
                conn.close()
            except:
                pass
        
        return jsonify({
            'error': f'Erreur lors de l\'approbation: {str(e)}'
        }), 500

@app.route('/admin/reject-transaction/<int:transaction_id>', methods=['POST'])
@admin_required
def reject_transaction(transaction_id):
    """Rejeter une transaction"""
    data = request.get_json()
    reason = data.get('reason', 'Transaction rejetée par l\'administrateur')

    conn = get_db_connection()

    try:
        # Récupérer la transaction
        transaction = conn.execute('''
            SELECT t.*, u.email, u.first_name
            FROM transactions t
            JOIN users u ON t.user_id = u.id
            WHERE t.id = ?
        ''', (transaction_id,)).fetchone()

        if not transaction:
            return jsonify({'error': 'Transaction non trouvée'}), 404

        if transaction['type'] == 'withdrawal':
            # Rembourser le montant au solde utilisateur
            conn.execute('''
                UPDATE users 
                SET balance = balance + ? 
                WHERE id = ?
            ''', (transaction['amount'], transaction['user_id']))

        # Marquer comme rejetée
        conn.execute('''
            UPDATE transactions 
            SET status = 'failed' 
            WHERE id = ?
        ''', (transaction_id,))

        # Ajouter notification
        add_notification(
            transaction['user_id'],
            'Transaction rejetée',
            f'Votre {transaction["type"]} de {transaction["amount"]} USDT a été rejetée. Raison: {reason}',
            'error'
        )

        conn.commit()

        return jsonify({'success': True, 'message': 'Transaction rejetée'})

    except Exception as e:
        conn.rollback()
        return jsonify({'error': f'Erreur: {str(e)}'}), 500
    finally:
        conn.close()

@app.route('/admin/support')
@admin_required
def admin_support():
    """Gestion des tickets de support"""
    conn = get_db_connection()

    try:
        tickets = conn.execute('''
            SELECT st.*, u.first_name, u.last_name, u.email,
                   (SELECT COUNT(*) FROM support_messages sm WHERE sm.ticket_id = st.id) as message_count
            FROM support_tickets st
            JOIN users u ON st.user_id = u.id
            ORDER BY st.created_at DESC
        ''').fetchall()
    except:
        tickets = []

    conn.close()

    return render_template('admin_support.html', tickets=tickets)

@app.route('/admin/support/ticket/<int:ticket_id>')
@admin_required
def admin_support_ticket(ticket_id):
    """Voir les détails d'un ticket de support"""
    conn = get_db_connection()

    # Récupérer le ticket
    ticket = conn.execute('''
        SELECT st.*, u.first_name, u.last_name, u.email
        FROM support_tickets st
        JOIN users u ON st.user_id = u.id
        WHERE st.id = ?
    ''', (ticket_id,)).fetchone()

    if not ticket:
        flash('Ticket non trouvé', 'error')
        return redirect(url_for('admin_support'))

    # Récupérer les messages
    messages = conn.execute('''
        SELECT sm.*, u.first_name, u.last_name
        FROM support_messages sm
        LEFT JOIN users u ON sm.user_id = u.id
        WHERE sm.ticket_id = ?
        ORDER BY sm.created_at ASC
    ''', (ticket_id,)).fetchall()

    conn.close()

    return render_template('admin_support_ticket.html', ticket=ticket, messages=messages)

@app.route('/admin/support/reply', methods=['POST'])
@admin_required
def admin_support_reply():
    """Répondre à un ticket de support"""
    data = request.get_json()
    ticket_id = data.get('ticket_id')
    message = data.get('message', '').strip()

    if not message:
        return jsonify({'error': 'Message requis'}), 400

    conn = get_db_connection()

    try:
        # Ajouter la réponse admin
        conn.execute('''
            INSERT INTO support_messages (ticket_id, message, is_admin)
            VALUES (?, ?, 1)
        ''', (ticket_id, message))

        # Mettre à jour le statut du ticket
        conn.execute('''
            UPDATE support_tickets 
            SET status = 'admin_reply'
            WHERE id = ?
        ''', (ticket_id,))

        # Récupérer les infos du ticket pour notification
        ticket = conn.execute('''
            SELECT st.*, u.first_name, u.email
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
                f'Vous avez reçu une réponse à votre ticket #{ticket_id}',
                'info'
            )

        return jsonify({'success': True})

    except Exception as e:
        conn.rollback()
        return jsonify({'error': f'Erreur: {str(e)}'}), 500
    finally:
        conn.close()

@app.route('/admin/support/close/<int:ticket_id>', methods=['POST'])
@admin_required
def admin_close_ticket(ticket_id):
    """Fermer un ticket de support"""
    conn = get_db_connection()

    try:
        # Récupérer les infos du ticket
        ticket = conn.execute('''
            SELECT user_id, subject FROM support_tickets WHERE id = ?
        ''', (ticket_id,)).fetchone()

        if not ticket:
            return jsonify({'error': 'Ticket non trouvé'}), 404

        # Fermer le ticket
        conn.execute('''
            UPDATE support_tickets 
            SET status = 'closed'
            WHERE id = ?
        ''', (ticket_id,))

        conn.commit()

        # Notification utilisateur
        add_notification(
            ticket['user_id'],
            'Ticket fermé',
            f'Votre ticket #{ticket_id} a été fermé par l\'équipe support',
            'info'
        )

        return jsonify({'success': True})

    except Exception as e:
        conn.rollback()
        return jsonify({'error': f'Erreur: {str(e)}'}), 500
    finally:
        conn.close()

@app.route('/admin/calculate-profits', methods=['POST'])
@admin_required
def admin_calculate_profits():
    """Déclencher manuellement le calcul des profits quotidiens"""
    try:
        calculate_daily_profits()
        return jsonify({
            'success': True, 
            'message': 'Profits quotidiens calculés avec succès!'
        })
    except Exception as e:
        return jsonify({
            'error': f'Erreur lors du calcul des profits: {str(e)}'
        }), 500

@app.route('/calculate-profits-now', methods=['POST'])
@login_required  
def user_calculate_profits():
    """Permettre aux utilisateurs de déclencher le calcul des profits"""
    try:
        calculate_daily_profits()
        return jsonify({
            'success': True, 
            'message': 'Vos profits ont été recalculés!'
        })
    except Exception as e:
        return jsonify({
            'error': f'Erreur lors du calcul des profits: {str(e)}'
        }), 500

@app.route('/restore-investments', methods=['POST'])
@login_required
def restore_investments():
    """Restaurer les investissements perdus d'un utilisateur"""
    try:
        # Vérifier s'il n'y a vraiment aucun investissement actif
        conn = get_db_connection()
        active_count = conn.execute('''
            SELECT COUNT(*) as count 
            FROM user_investments 
            WHERE user_id = ? AND is_active = 1
        ''', (session['user_id'],)).fetchone()['count']
        
        if active_count > 0:
            conn.close()
            return jsonify({
                'error': 'Vous avez déjà des investissements actifs'
            }), 400
        
        conn.close()
        
        # Restaurer avec des investissements de base
        success = restore_user_investments(session['user_id'])
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Vos investissements ont été restaurés! Rechargez la page pour les voir.'
            })
        else:
            return jsonify({
                'error': 'Erreur lors de la restauration'
            }), 500
            
    except Exception as e:
        return jsonify({
            'error': f'Erreur: {str(e)}'
        }), 500

# Security Routes
@app.route('/security')
@login_required
def security_settings():
    """Page des paramètres de sécurité"""
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()

    # Créer la table security_logs si elle n'existe pas
    try:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS security_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                details TEXT,
                ip_address TEXT,
                user_agent TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        conn.commit()
    except Exception as e:
        print(f"Erreur création table security_logs: {e}")

    # Récupérer les logs de sécurité récents
    try:
        security_logs = conn.execute('''
            SELECT * FROM security_logs 
            WHERE user_id = ? 
            ORDER BY created_at DESC 
            LIMIT 10
        ''', (session['user_id'],)).fetchall()
    except Exception as e:
        print(f"Erreur récupération logs: {e}")
        security_logs = []

    conn.close()

    return render_template('security.html', user=user, security_logs=security_logs)

@app.route('/change-password', methods=['POST'])
@login_required
def change_password():
    """Changer le mot de passe"""
    data = request.get_json()
    current_password = data.get('current_password')
    new_password = data.get('new_password')
    confirm_password = data.get('confirm_password')

    if not all([current_password, new_password, confirm_password]):
        return jsonify({'error': 'Tous les champs sont requis'}), 400

    if new_password != confirm_password:
        return jsonify({'error': 'Les nouveaux mots de passe ne correspondent pas'}), 400

    if len(new_password) < 8:
        return jsonify({'error': 'Le mot de passe doit contenir au moins 8 caractères'}), 400

    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()

    # Vérifier l'ancien mot de passe
    if not check_password_hash(user['password_hash'], current_password):
        conn.close()
        return jsonify({'error': 'Mot de passe actuel incorrect'}), 401

    # Mettre à jour le mot de passe
    new_password_hash = generate_password_hash(new_password)
    conn.execute('''
        UPDATE users 
        SET password_hash = ? 
        WHERE id = ?
    ''', (new_password_hash, session['user_id']))

    # Enregistrer dans les logs de sécurité
    log_security_action(session['user_id'], 'password_changed', 'Mot de passe modifié avec succès')

    conn.commit()
    conn.close()

    # Ajouter notification
    add_notification(
        session['user_id'],
        'Mot de passe modifié',
        'Votre mot de passe a été modifié avec succès.',
        'success'
    )

    return jsonify({'success': True, 'message': 'Mot de passe modifié avec succès'})

@app.route('/enable-2fa', methods=['POST'])
@login_required
def enable_2fa():
    """Activer l'authentification 2FA"""
    import pyotp
    import qrcode
    import io
    import base64

    try:
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()

        if user['two_fa_enabled']:
            return jsonify({'error': '2FA déjà activé'}), 400

        # Générer une clé secrète pour l'utilisateur
        secret = pyotp.random_base32()

        # Créer l'URI pour le QR code
        totp_uri = pyotp.totp.TOTP(secret).provisioning_uri(
            user['email'], 
            issuer_name="InvestCrypto Pro"
        )

        # Générer le QR code
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(totp_uri)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        # Convertir en base64
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        qr_code_b64 = base64.b64encode(buffer.getvalue()).decode()

        # Stocker temporairement la clé secrète
        conn.execute('''
            UPDATE users 
            SET two_fa_secret = ? 
            WHERE id = ?
        ''', (secret, session['user_id']))

        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'secret': secret,
            'qr_code': f"data:image/png;base64,{qr_code_b64}",
            'manual_entry_key': secret
        })

    except ImportError:
        return jsonify({'error': 'Modules 2FA non disponibles. Installez pyotp et qrcode'}), 500
    except Exception as e:
        return jsonify({'error': f'Erreur lors de l\'activation 2FA: {str(e)}'}), 500

@app.route('/verify-2fa', methods=['POST'])
@login_required
def verify_2fa():
    """Vérifier et finaliser l'activation 2FA"""
    import pyotp

    try:
        data = request.get_json()
        token = data.get('token')

        if not token:
            return jsonify({'error': 'Code de vérification requis'}), 400

        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()

        if not user['two_fa_secret']:
            return jsonify({'error': 'Processus 2FA non initié'}), 400

        # Vérifier le token
        totp = pyotp.TOTP(user['two_fa_secret'])
        if not totp.verify(token, valid_window=1):
            return jsonify({'error': 'Code de vérification invalide'}), 400

        # Activer 2FA
        conn.execute('''
            UPDATE users 
            SET two_fa_enabled = 1 
            WHERE id = ?
        ''', (session['user_id'],))

        # Enregistrer dans les logs
        log_security_action(session['user_id'], '2fa_enabled', 'Authentification 2FA activée')

        conn.commit()
        conn.close()

        # Ajouter notification
        add_notification(
            session['user_id'],
            'Authentification 2FA activée',
            'Votre authentification à deux facteurs a été activée avec succès.',
            'success'
        )

        return jsonify({'success': True, 'message': 'Authentification 2FA activée avec succès'})

    except ImportError:
        return jsonify({'error': 'Modules 2FA non disponibles'}), 500
    except Exception as e:
        return jsonify({'error': f'Erreur lors de la vérification: {str(e)}'}), 500

@app.route('/disable-2fa', methods=['POST'])
@login_required
def disable_2fa():
    """Désactiver l'authentification 2FA"""
    data = request.get_json()
    password = data.get('password')

    if not password:
        return jsonify({'error': 'Mot de passe requis pour désactiver 2FA'}), 400

    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()

    # Vérifier le mot de passe
    if not check_password_hash(user['password_hash'], password):
        conn.close()
        return jsonify({'error': 'Mot de passe incorrect'}), 401

    # Désactiver 2FA
    conn.execute('''
        UPDATE users 
        SET two_fa_enabled = 0, two_fa_secret = NULL 
        WHERE id = ?
    ''', (session['user_id'],))

    # Enregistrer dans les logs
    log_security_action(session['user_id'], '2fa_disabled', 'Authentification 2FA désactivée')

    conn.commit()
    conn.close()

    # Ajouter notification
    add_notification(
        session['user_id'],
        'Authentification 2FA désactivée',
        'Votre authentification à deux facteurs a été désactivée.',
        'warning'
    )

    return jsonify({'success': True, 'message': 'Authentification 2FA désactivée'})

def update_admin_password(email, new_password):
    """Mettre à jour le mot de passe d'un administrateur existant"""
    try:
        conn = get_db_connection()

        # Vérifier si l'admin existe
        existing_admin = conn.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
        if existing_admin:
            password_hash = generate_password_hash(new_password)
            conn.execute('UPDATE users SET password_hash = ? WHERE email = ?', (password_hash, email))
            conn.commit()
            conn.close()
            print(f"✅ Mot de passe mis à jour pour {email}")
            return True
        else:
            print(f"❌ Administrateur {email} non trouvé")
            conn.close()
            return False

    except Exception as e:
        print(f"❌ Erreur mise à jour mot de passe: {e}")
        return False

def create_secure_admin(email, password, first_name="Admin", last_name="System"):
    """Créer un compte administrateur sécurisé"""
    try:
        conn = get_db_connection()

        # Vérifier si l'admin existe déjà
        existing_admin = conn.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
        if existing_admin:
            print(f"⚠️ Administrateur {email} existe déjà")
            # Mettre à jour le mot de passe si différent
            update_admin_password(email, password)
            conn.close()
            return False

        # Créer le compte admin
        password_hash = generate_password_hash(password)
        referral_code = generate_referral_code()

        cursor = conn.execute('''
            INSERT INTO users (email, password_hash, first_name, last_name, referral_code, kyc_status, balance)
            VALUES (?, ?, ?, ?, ?, 'verified', 0.0)
        ''', (email, password_hash, first_name, last_name, referral_code))

        admin_id = cursor.lastrowid
        conn.commit()
        conn.close()

        print(f"✅ Administrateur {email} créé avec succès (ID: {admin_id})")
        return True

    except Exception as e:
        print(f"❌ Erreur création admin: {e}")
        return False

def log_security_action(user_id, action, details=""):
    """Enregistrer une action de sécurité"""
    try:
        conn = get_db_connection()

        # Créer table de logs de sécurité si elle n'existe pas
        conn.execute('''
            CREATE TABLE IF NOT EXISTS security_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                details TEXT,
                ip_address TEXT,
                user_agent TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')

        # Récupérer l'IP et User-Agent depuis Flask si disponible
        ip_address = None
        user_agent = None
        try:
            from flask import request
            ip_address = request.remote_addr
            user_agent = request.headers.get('User-Agent', '')
        except:
            pass

        conn.execute('''
            INSERT INTO security_logs (user_id, action, details, ip_address, user_agent)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, action, details, ip_address, user_agent))

        conn.commit()
        conn.close()

    except Exception as e:
        print(f"❌ Erreur log sécurité: {e}")

if __name__ == '__main__':
    # Initialize database with retry logic
    max_init_retries = 3
    for init_attempt in range(max_init_retries):
        try:
            init_db()
            print("✅ Base de données initialisée avec succès")
            break
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and init_attempt < max_init_retries - 1:
                print(f"⚠️ Base de données verrouillée, tentative {init_attempt + 1}/{max_init_retries}")
                import time
                time.sleep(2)
                continue
            else:
                print(f"❌ Erreur initialisation DB: {e}")
                break
        except Exception as e:
            print(f"❌ Erreur inattendue initialisation: {e}")
            break

    # Créer les comptes administrateur sécurisés
    print("🔐 Initialisation des comptes administrateur...")
    create_secure_admin('admin@investcryptopro.com', 'AdminSecure2024!', 'Admin', 'Principal')
    create_secure_admin('support@investcryptopro.com', 'SupportSecure2024!', 'Support', 'Team')
    create_secure_admin('security@investcryptopro.com', 'SecuritySecure2024!', 'Security', 'Team')
    create_secure_admin('a@gmail.com', 'aaaaaa', 'Admin', 'User')

    # Mettre à jour le mot de passe du compte a@gmail.com
    update_admin_password('a@gmail.com', 'aaaaaa')

    # Setup scheduler for daily profit calculation
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=calculate_daily_profits,
        trigger="cron",
        hour=0,
        minute=0,
        id='daily_profits'
    )
    scheduler.start()

    # Shutdown scheduler when exiting the app
    atexit.register(lambda: scheduler.shutdown())

    app.run(host='0.0.0.0', port=5000, debug=True)