
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
    
    # Insert default ROI plans
    cursor.execute('''
        INSERT OR IGNORE INTO roi_plans (name, description, daily_rate, duration_days, min_amount, max_amount)
        VALUES 
        ('Plan Débutant', 'Parfait pour commencer', 0.05, 30, 50, 1000),
        ('Plan Intermédiaire', 'Rendement équilibré', 0.08, 45, 500, 5000),
        ('Plan Premium', 'Rendement élevé', 0.12, 60, 1000, 10000),
        ('Plan VIP', 'Rendement exceptionnel', 0.15, 90, 5000, 50000)
    ''')
    
    # Insert sample projects
    cursor.execute('''
        INSERT OR IGNORE INTO projects (title, description, category, target_amount, expected_return, duration_months, min_investment, max_investment, deadline)
        VALUES 
        ('Ferme Solaire Éco', 'Projet de ferme solaire écologique avec retour sur investissement garanti', 'Énergie', 50000, 0.20, 18, 100, 5000, datetime("now", "+60 days")),
        ('Immobilier Résidentiel', 'Développement immobilier dans une zone en expansion', 'Immobilier', 100000, 0.25, 24, 500, 10000, datetime("now", "+90 days")),
        ('Agriculture Bio', 'Projet d''agriculture biologique avec débouchés garantis', 'Agriculture', 30000, 0.18, 12, 200, 3000, datetime("now", "+45 days"))
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
    notifications = conn.execute('''
        SELECT * FROM notifications 
        WHERE user_id = ? AND is_read = 0
        ORDER BY created_at DESC
        LIMIT 5
    ''', (session['user_id'],)).fetchall()
    
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
    
    conn.close()
    
    return render_template('profile.html', user=user, referrals=referrals)

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
    
    # Shutdown scheduler when exiting the app
    atexit.register(lambda: scheduler.shutdown())
    
    app.run(host='0.0.0.0', port=5000, debug=True)
