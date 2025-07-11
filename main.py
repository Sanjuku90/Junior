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

# Import du bot Telegram utilisateur uniquement
TELEGRAM_ENABLED = False
try:
    from telegram_investment_bot import setup_user_telegram_bot
    TELEGRAM_USER_BOT_ENABLED = True
except ImportError:
    TELEGRAM_USER_BOT_ENABLED = False
    print("Bot Telegram utilisateur non disponible")

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
        ('Renewable Energy', '🌱 Énergies renouvelables ! 30% de retour en 20 mois.', 'Écologie', 40000, 0.30, 20, 20, 4000, datetime("now", "+65 days")),
        ('Biotech Innovation', '🧬 Innovation biotechnologique ! 35% de retour en 24 mois.', 'Biotechnologie', 60000, 0.35, 24, 20, 6000, datetime("now", "+80 days")),
        ('Space Technology', '🚀 Technologie spatiale ! 40% de retour en 30 mois.', 'Espace', 80000, 0.40, 30, 20, 8000, datetime("now", "+90 days")),
        ('Quantum Computing', '⚛️ Informatique quantique ! 50% de retour en 36 mois.', 'Quantique', 100000, 0.50, 36, 20, 10000, datetime("now", "+120 days"))
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

    # Notification admin supprimée - traitement manuel requis

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

    # Notification admin supprimée - traitement manuel requis

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

    # Setup du bot utilisateur uniquement
    if TELEGRAM_USER_BOT_ENABLED:
        user_bot_app = setup_user_telegram_bot()
        if user_bot_app:
            def run_user_bot():
                try:
                    import asyncio
                    import signal
                    
                    # Créer un nouveau loop pour ce thread
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                    async def start_user_bot():
                        try:
                            print("🚀 Initialisation du bot utilisateur...")
                            await user_bot_app.initialize()
                            await user_bot_app.start()
                            print("✅ Bot utilisateur en cours d'exécution")
                            
                            # Utiliser l'updater pour le polling avec gestion d'erreur
                            await user_bot_app.updater.start_polling(
                                allowed_updates=["message", "callback_query"],
                                drop_pending_updates=True,
                                error_callback=lambda exc: print(f"⚠️ Erreur bot ignorée: {exc}")
                            )
                            
                            # Garder le bot en vie
                            stop_event = asyncio.Event()
                            
                            def signal_handler():
                                stop_event.set()
                            
                            # Attendre indéfiniment ou jusqu'à interruption
                            try:
                                await stop_event.wait()
                            except (KeyboardInterrupt, SystemExit):
                                stop_event.set()
                            
                        except Exception as e:
                            if "Conflict" in str(e):
                                print(f"⚠️ Bot déjà en cours d'exécution elsewhere: {e}")
                            else:
                                print(f"❌ Erreur bot utilisateur: {e}")
                        finally:
                            try:
                                await user_bot_app.updater.stop()
                                await user_bot_app.stop()
                                print("🛑 Bot utilisateur arrêté")
                            except:
                                pass
                    
                    # Exécuter le bot dans son propre loop
                    loop.run_until_complete(start_user_bot())
                    
                except Exception as e:
                    if "Conflict" not in str(e):
                        print(f"❌ Erreur Telegram bot utilisateur: {e}")

            user_thread = threading.Thread(target=run_user_bot, daemon=True)
            user_thread.start()
            print("✅ Thread bot Telegram utilisateur démarré")
        else:
            print("❌ Échec de la configuration du bot utilisateur")
    else:
        print("❌ Bot Telegram utilisateur non disponible")

    # Shutdown scheduler when exiting the app
    atexit.register(lambda: scheduler.shutdown())

    app.run(host='0.0.0.0', port=5000, debug=False)