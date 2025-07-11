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
from apscheduler.schedulers.background import BackgroundScheduler
import atexit

# Import du bot Telegram
try:
    from telegram_bot import notify_deposit_request, notify_withdrawal_request, setup_telegram_bot, stop_telegram_bot
    TELEGRAM_ENABLED = True
except ImportError:
    TELEGRAM_ENABLED = False
    print("Bot Telegram non disponible - fonctionnalités de confirmation désactivées")

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
            two_fa_enabled BOOLEAN DEFAULT 0
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
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

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

    # Insert default ROI plans - Minimum 20 USDT pour tous les plans
    cursor.execute('''
        INSERT OR IGNORE INTO roi_plans (name, description, daily_rate, duration_days, min_amount, max_amount)
        VALUES 
        ('Plan Débutant', '🚀 Idéal pour débuter dans l''investissement crypto ! Commencez avec seulement 20$ et recevez 5% de profit quotidien automatiquement. Parfait pour tester notre plateforme et comprendre le potentiel des investissements crypto. Retour total de 150% en 30 jours !', 0.05, 30, 20, 1000),
        ('Plan Intermédiaire', '💎 Notre plan le plus équilibré ! 8% de rendement quotidien garanti pendant 45 jours. Stratégie diversifiée sur plusieurs crypto-monnaies pour optimiser les gains. Capital + profits = 360% de retour total. Idéal pour les investisseurs avisés cherchant un bon équilibre risque/rendement.', 0.08, 45, 20, 5000),
        ('Plan Premium', '⭐ CHOIX POPULAIRE ! 12% de profit quotidien pendant 60 jours avec notre algorithme de trading avancé. Accès prioritaire aux nouvelles opportunités d''investissement. Support client VIP 24/7. Retour total exceptionnel de 720% ! Recommandé par 95% de nos clients.', 0.12, 60, 20, 10000),
        ('Plan VIP', '👑 EXCLUSIF pour les gros investisseurs ! 15% de rendement quotidien pendant 90 jours grâce à notre pool de liquidité premium. Gestionnaire de compte personnel, analyses de marché exclusives, accès aux ICO privées. Retour total de 1350% ! Rejoignez l''élite des investisseurs crypto.', 0.15, 90, 20, 50000)
    ''')

    # Insert default Staking plans - Minimum 20 USDT pour accessibilité
    cursor.execute('''
        INSERT OR IGNORE INTO staking_plans (name, description, duration_days, annual_rate, min_amount, max_amount, penalty_rate)
        VALUES 
        ('Staking Flexible', '🔄 Parfait pour débuter ! Stakez vos cryptos pendant seulement 15 jours et gagnez 12% par an. Flexibilité maximale avec possibilité de retrait anticipé (3% de pénalité). Idéal pour tester le staking sans engagement long terme. Profits calculés et versés automatiquement !', 15, 0.12, 20, 5000, 0.03),
        ('Staking Standard', '⚖️ L''équilibre parfait ! 30 jours de staking pour 18% de rendement annuel. Notre plan le plus populaire alliant sécurité et rentabilité. Vos tokens sont sécurisés dans notre pool de validation. Récompenses distribuées proportionnellement à votre participation.', 30, 0.18, 20, 10000, 0.05),
        ('Staking Premium', '💰 Pour les vrais HODLers ! 90 jours de staking pour un rendement exceptionnel de 25% par an. Participez activement à la sécurisation du réseau blockchain. Bonus de fidélité inclus. Pénalité de 8% pour retrait anticipé car nous privilégions la stabilité long terme.', 90, 0.25, 20, 25000, 0.08)
    ''')

    # Insert default Frozen plans - Minimum 20 USDT pour tous
    cursor.execute('''
        INSERT OR IGNORE INTO frozen_plans (name, description, duration_days, total_return_rate, min_amount, max_amount)
        VALUES 
        ('Plan Diamant', '💎 INVESTISSEMENT PREMIUM ! Vos fonds sont gelés pendant 6 mois dans notre programme exclusif de yield farming. 250% de retour GARANTI grâce à nos partenariats avec les plus grandes DeFi. Vos tokens travaillent 24/7 dans des pools de liquidité ultra-rentables. Aucun stress, aucune volatilité - juste des gains assurés !', 180, 2.5, 20, 50000),
        ('Plan Platinum', '🏆 L''ÉLITE DES INVESTISSEMENTS ! 12 mois pour 400% de retour total ! Vos fonds sont déployés dans notre stratégie propriétaire combinant arbitrage, DeFi farming et participation aux gouvernances. Accès exclusif aux projets les plus prometteurs du marché crypto. Un an d''attente pour une vie de profits !', 365, 4.0, 20, 100000)
    ''')

    # Insert sample projects - Minimum 20 USDT pour l'accessibilité
    cursor.execute('''
        INSERT OR IGNORE INTO projects (title, description, category, target_amount, expected_return, duration_months, min_investment, max_investment, deadline)
        VALUES 
        ('Ferme Solaire Éco', '☀️ RÉVOLUTIONNEZ L''ÉNERGIE ! Investissez dans la plus grande ferme solaire d''Afrique de l''Ouest. 500 hectares de panneaux dernière génération avec contrats gouvernementaux sur 20 ans. 20% de retour GARANTI grâce aux tarifs de rachat préférentiels. Impact environnemental positif + profits assurés. Déjà 78% financé !', 'Énergie', 50000, 0.20, 18, 20, 5000, datetime("now", "+60 days")),
        ('Immobilier Résidentiel', '🏠 OPPORTUNITÉ EN OR ! Complexe résidentiel de luxe dans la nouvelle zone économique spéciale. 200 appartements haut de gamme avec pré-ventes déjà à 65%. Promoteur expérimenté avec 15 ans de succès. 25% de retour sur 24 mois grâce à la plus-value et aux loyers. Défiscalisation possible !', 'Immobilier', 100000, 0.25, 24, 20, 10000, datetime("now", "+90 days")),
        ('Agriculture Bio', '🌱 NOURRISSEZ L''AVENIR ! Ferme bio moderne de 100 hectares avec techniques permaculture avancées. Contrats exclusifs avec grandes chaînes de distribution bio. 18% de retour en 12 mois grâce à la demande croissante pour le bio. Agriculture 4.0 avec IoT et intelligence artificielle. Impact social et environnemental fort !', 'Agriculture', 30000, 0.18, 12, 20, 3000, datetime("now", "+45 days"))
    ''')

    conn.commit()
    conn.close()

# Authentication decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Admin decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('is_admin') != True:
            flash('Accès refusé. Privilèges administrateur requis.', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# Utility functions
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

# Scheduled tasks
def calculate_daily_profits():
    conn = get_db_connection()
    active_investments = conn.execute('''
        SELECT ui.*, u.email, rp.name as plan_name
        FROM user_investments ui
        JOIN users u ON ui.user_id = u.id
        JOIN roi_plans rp ON ui.plan_id = rp.id
        WHERE ui.is_active = 1 AND ui.end_date > datetime('now')
    ''').fetchall()

    for investment in active_investments:
        # Calculate daily profit
        daily_profit = investment['daily_profit']

        # Update user balance
        conn.execute('''
            UPDATE users 
            SET balance = balance + ? 
            WHERE id = ?
        ''', (daily_profit, investment['user_id']))

        # Update total earned
        conn.execute('''
            UPDATE user_investments 
            SET total_earned = total_earned + ? 
            WHERE id = ?
        ''', (daily_profit, investment['id']))

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

    # Check for completed investments
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
            session['is_admin'] = (user['email'] == 'admin@example.com')  # Simple admin check

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
        WHERE ui.user_id = ? AND ui.is_active = 1
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

    # Convert notifications to dict and parse datetime
    notifications = []
    for notif in notifications_raw:
        notif_dict = dict(notif)
        if notif_dict['created_at']:
            try:
                notif_dict['created_at'] = datetime.fromisoformat(notif_dict['created_at'].replace('Z', '+00:00'))
            except:
                notif_dict['created_at'] = None
        notifications.append(notif_dict)

    conn.close()

    return render_template('dashboard.html', 
                         user=user, 
                         investments=investments, 
                         project_investments=project_investments,
                         notifications=notifications)

@app.route('/roi-plans')
@login_required
def roi_plans():
    conn = get_db_connection()
    plans = conn.execute('SELECT * FROM roi_plans WHERE is_active = 1').fetchall()
    conn.close()

    return render_template('roi_plans.html', plans=plans)

@app.route('/invest-roi', methods=['POST'])
@login_required
def invest_roi():
    data = request.get_json()
    plan_id = data.get('plan_id')
    amount = float(data.get('amount', 0))

    conn = get_db_connection()

    # Get plan details
    plan = conn.execute('SELECT * FROM roi_plans WHERE id = ?', (plan_id,)).fetchone()
    if not plan:
        return jsonify({'error': 'Plan non trouvé'}), 404

    # Check amount limits
    if amount < plan['min_amount'] or amount > plan['max_amount']:
        return jsonify({'error': f'Montant doit être entre {plan["min_amount"]} et {plan["max_amount"]} USDT'}), 400

    # Check user balance
    user = conn.execute('SELECT balance FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    if user['balance'] < amount:
        return jsonify({'error': 'Solde insuffisant'}), 400

    # Calculate dates and profit
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
        VALUES (?, 'investment', ?, 'completed', ?)
    ''', (session['user_id'], amount, generate_transaction_hash()))

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'Investissement réalisé avec succès!'})

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

    # Notifier l'admin via Telegram
    if TELEGRAM_ENABLED:
        notify_deposit_request(session['user_id'], amount, transaction_hash, deposit_id)

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

    # Notifier l'admin via Telegram
    if TELEGRAM_ENABLED:
        notify_withdrawal_request(session['user_id'], amount, withdrawal_address, withdrawal_id)

    # Ajouter une notification à l'utilisateur
    add_notification(
        session['user_id'],
        'Retrait en cours de traitement',
        f'Votre demande de retrait de {amount} USDT est en cours de traitement.',
        'info'
    )

    return jsonify({'success': True, 'message': 'Demande de retrait soumise pour traitement'})

@app.route('/admin')
@admin_required
def admin_dashboard():
    conn = get_db_connection()

    # Get stats
    stats = {
        'total_users': conn.execute('SELECT COUNT(*) as count FROM users').fetchone()['count'],
        'total_investments': conn.execute('SELECT COALESCE(SUM(amount), 0) as total FROM user_investments').fetchone()['total'],
        'total_projects': conn.execute('SELECT COUNT(*) as count FROM projects').fetchone()['count'],
        'pending_kyc': conn.execute('SELECT COUNT(*) as count FROM users WHERE kyc_status = "pending"').fetchone()['count']
    }

    # Get recent transactions
    transactions = conn.execute('''
        SELECT t.*, u.email, u.first_name, u.last_name
        FROM transactions t
        JOIN users u ON t.user_id = u.id
        ORDER BY t.created_at DESC
        LIMIT 10
    ''').fetchall()

    conn.close()

    return render_template('admin_dashboard.html', stats=stats, transactions=transactions)

if __name__ == '__main__':
    init_db()

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

    # Setup Telegram bots si disponibles
    if TELEGRAM_ENABLED:
        # Bot admin
        telegram_app = setup_telegram_bot()
        if telegram_app:
            def run_admin_bot():
                try:
                    import asyncio

                    async def start_admin_bot():
                        try:
                            await telegram_app.initialize()
                            await telegram_app.start()
                            await telegram_app.updater.start_polling(
                                allowed_updates=["message", "callback_query"],
                                drop_pending_updates=True
                            )
                            await telegram_app.updater.idle()
                        except Exception as e:
                            print(f"❌ Erreur bot admin: {e}")
                        finally:
                            await telegram_app.stop()

                    asyncio.run(start_admin_bot())
                except Exception as e:
                    print(f"❌ Erreur Telegram bot admin: {e}")

            admin_thread = threading.Thread(target=run_admin_bot, daemon=True)
            admin_thread.start()
            print("✅ Bot Telegram d'administration démarré")

        # Bot utilisateur
        try:
            from telegram_investment_bot import setup_user_telegram_bot
            
            # Vérifier si le token utilisateur est configuré
            user_token = os.getenv('TELEGRAM_BOT_TOKEN_USER')
            if not user_token:
                print("⚠️  TELEGRAM_BOT_TOKEN_USER non configuré - Bot utilisateur désactivé")
                print("💡 Ajoutez votre token de bot dans les Secrets pour activer le bot utilisateur")
            else:
                user_bot_app = setup_user_telegram_bot()
                if user_bot_app:
                    def run_user_bot():
                        try:
                            import asyncio

                            async def start_user_bot():
                                try:
                                    print("🚀 Initialisation du bot utilisateur...")
                                    await user_bot_app.initialize()
                                    await user_bot_app.start()
                                    await user_bot_app.updater.start_polling(
                                        allowed_updates=["message", "callback_query"],
                                        drop_pending_updates=True
                                    )
                                    print("✅ Bot utilisateur en cours d'exécution")
                                    await user_bot_app.updater.idle()
                                except Exception as e:
                                    print(f"❌ Erreur bot utilisateur: {e}")
                                finally:
                                    try:
                                        await user_bot_app.stop()
                                    except:
                                        pass

                            asyncio.run(start_user_bot())
                        except Exception as e:
                            print(f"❌ Erreur Telegram bot utilisateur: {e}")

                    user_thread = threading.Thread(target=run_user_bot, daemon=True)
                    user_thread.start()
                    print("✅ Thread du bot Telegram utilisateur démarré")
                else:
                    print("❌ Échec de la configuration du bot utilisateur")
        except ImportError as e:
            print(f"❌ Module bot utilisateur non disponible: {e}")
    else:
        print("❌ Telegram non activé")

    # Shutdown scheduler and telegram bot when exiting the app
    atexit.register(lambda: scheduler.shutdown())
    if TELEGRAM_ENABLED:
        atexit.register(lambda: stop_telegram_bot())

    app.run(host='0.0.0.0', port=5000, debug=True)