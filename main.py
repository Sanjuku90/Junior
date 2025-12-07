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

# Utilisation de SQLite pour la persistance
REPLIT_DB_AVAILABLE = False
print("✅ Utilisation de SQLite pour la persistance des données")

# Import du bot Telegram utilisateur uniquement
TELEGRAM_ENABLED = False
TELEGRAM_USER_BOT_ENABLED = False


app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

# Configuration PWA
@app.route('/static/sw.js')
def service_worker():
    return app.send_static_file('sw.js'), 200, {'Content-Type': 'application/javascript'}

@app.route('/static/manifest.json')
def manifest():
    return app.send_static_file('manifest.json'), 200, {'Content-Type': 'application/json'}

@app.route('/static/offline.html')
def offline():
    return app.send_static_file('offline.html')

# Configuration avec persistance
if REPLIT_DB_AVAILABLE:
    # Utiliser un répertoire persistant pour la base de données
    DATABASE = '/home/runner/.local/share/investment_platform.db'
    # S'assurer que le répertoire existe
    os.makedirs(os.path.dirname(DATABASE), exist_ok=True)
    print(f"📂 Base de données persistante: {DATABASE}")
else:
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

def backup_critical_data():
    """Sauvegarder les données critiques dans Replit DB"""
    if not REPLIT_DB_AVAILABLE:
        return
    
    try:
        conn = get_db_connection()
        
        # Sauvegarder TOUS les investissements ROI (actifs et terminés)
        all_investments = conn.execute('''
            SELECT * FROM user_investments ORDER BY start_date DESC
        ''').fetchall()
        
        investments_data = []
        for inv in all_investments:
            investments_data.append(dict(inv))
        
        replit_db['all_investments_history'] = json.dumps(investments_data, default=str)
        
        # Sauvegarder TOUS les investissements staking (actifs et terminés)
        all_staking = conn.execute('''
            SELECT * FROM user_staking ORDER BY start_date DESC
        ''').fetchall()
        
        staking_data = []
        for stake in all_staking:
            staking_data.append(dict(stake))
        
        replit_db['all_staking_history'] = json.dumps(staking_data, default=str)
        
        # Sauvegarder TOUS les bots de trading (actifs et terminés)
        all_bots = conn.execute('''
            SELECT * FROM user_trading_bots ORDER BY start_date DESC
        ''').fetchall()
        
        bots_data = []
        for bot in all_bots:
            bots_data.append(dict(bot))
        
        replit_db['all_bots_history'] = json.dumps(bots_data, default=str)
        
        # Sauvegarder TOUS les copy trades (actifs et terminés)
        all_copy_trades = conn.execute('''
            SELECT * FROM user_copy_trading ORDER BY start_date DESC
        ''').fetchall()
        
        copy_trades_data = []
        for trade in all_copy_trades:
            copy_trades_data.append(dict(trade))
        
        replit_db['all_copy_trading_history'] = json.dumps(copy_trades_data, default=str)
        
        # Sauvegarder TOUS les investissements projets
        all_projects = conn.execute('''
            SELECT * FROM project_investments ORDER BY investment_date DESC
        ''').fetchall()
        
        projects_data = []
        for proj in all_projects:
            projects_data.append(dict(proj))
        
        replit_db['all_projects_history'] = json.dumps(projects_data, default=str)
        
        # Sauvegarder TOUTES les transactions
        all_transactions = conn.execute('''
            SELECT * FROM transactions ORDER BY created_at DESC
        ''').fetchall()
        
        transactions_data = []
        for trans in all_transactions:
            transactions_data.append(dict(trans))
        
        replit_db['all_transactions_history'] = json.dumps(transactions_data, default=str)
        
        # Sauvegarder les soldes utilisateurs
        users = conn.execute('SELECT id, email, balance, first_name, last_name FROM users').fetchall()
        users_data = []
        for user in users:
            users_data.append(dict(user))
        
        replit_db['user_balances'] = json.dumps(users_data, default=str)
        
        # Sauvegarder les plans pour restauration
        roi_plans = conn.execute('SELECT * FROM roi_plans').fetchall()
        roi_plans_data = []
        for plan in roi_plans:
            roi_plans_data.append(dict(plan))
        replit_db['roi_plans_backup'] = json.dumps(roi_plans_data, default=str)
        
        replit_db['last_backup'] = datetime.now().isoformat()
        conn.close()
        
        print("✅ Sauvegarde complète de l'historique effectuée")
        
    except Exception as e:
        print(f"❌ Erreur sauvegarde: {e}")

def restore_critical_data():
    """Restaurer les données critiques depuis Replit DB"""
    if not REPLIT_DB_AVAILABLE:
        return False
    
    try:
        # Vérifier s'il y a une sauvegarde disponible
        if 'last_backup' not in replit_db:
            return False
        
        conn = get_db_connection()
        
        print("🔄 Restauration de l'historique complet depuis la sauvegarde...")
        
        # Restaurer TOUS les investissements ROI
        if 'all_investments_history' in replit_db:
            investments_data = json.loads(replit_db['all_investments_history'])
            for inv in investments_data:
                try:
                    conn.execute('''
                        INSERT OR REPLACE INTO user_investments 
                        (id, user_id, plan_id, amount, start_date, end_date, daily_profit, total_earned, is_active, transaction_hash)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        inv.get('id'), inv.get('user_id'), inv.get('plan_id'), 
                        inv.get('amount'), inv.get('start_date'), inv.get('end_date'),
                        inv.get('daily_profit'), inv.get('total_earned', 0), 
                        inv.get('is_active', 1), inv.get('transaction_hash')
                    ))
                except Exception as e:
                    print(f"⚠️ Erreur restauration investissement {inv.get('id')}: {e}")
        
        # Restaurer TOUS les investissements staking
        if 'all_staking_history' in replit_db:
            staking_data = json.loads(replit_db['all_staking_history'])
            for stake in staking_data:
                try:
                    conn.execute('''
                        INSERT OR REPLACE INTO user_staking 
                        (id, user_id, plan_id, amount, start_date, end_date, is_active, is_withdrawn, total_earned, transaction_hash)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        stake.get('id'), stake.get('user_id'), stake.get('plan_id'),
                        stake.get('amount'), stake.get('start_date'), stake.get('end_date'),
                        stake.get('is_active', 1), stake.get('is_withdrawn', 0),
                        stake.get('total_earned', 0), stake.get('transaction_hash')
                    ))
                except Exception as e:
                    print(f"⚠️ Erreur restauration staking {stake.get('id')}: {e}")
        
        # Restaurer TOUS les bots de trading
        if 'all_bots_history' in replit_db:
            bots_data = json.loads(replit_db['all_bots_history'])
            for bot in bots_data:
                try:
                    conn.execute('''
                        INSERT OR REPLACE INTO user_trading_bots 
                        (id, user_id, strategy_id, amount, start_date, end_date, is_active, total_profit, daily_profit, last_profit_date, transaction_hash)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        bot.get('id'), bot.get('user_id'), bot.get('strategy_id'),
                        bot.get('amount'), bot.get('start_date'), bot.get('end_date'),
                        bot.get('is_active', 1), bot.get('total_profit', 0),
                        bot.get('daily_profit', 0), bot.get('last_profit_date'), bot.get('transaction_hash')
                    ))
                except Exception as e:
                    print(f"⚠️ Erreur restauration bot {bot.get('id')}: {e}")
        
        # Restaurer TOUS les copy trades
        if 'all_copy_trading_history' in replit_db:
            copy_trades_data = json.loads(replit_db['all_copy_trading_history'])
            for trade in copy_trades_data:
                try:
                    conn.execute('''
                        INSERT OR REPLACE INTO user_copy_trading 
                        (id, user_id, trader_id, amount, start_date, end_date, is_active, total_profit, copy_ratio, transaction_hash)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        trade.get('id'), trade.get('user_id'), trade.get('trader_id'),
                        trade.get('amount'), trade.get('start_date'), trade.get('end_date'),
                        trade.get('is_active', 1), trade.get('total_profit', 0),
                        trade.get('copy_ratio', 1.0), trade.get('transaction_hash')
                    ))
                except Exception as e:
                    print(f"⚠️ Erreur restauration copy trade {trade.get('id')}: {e}")
        
        # Restaurer TOUS les investissements projets
        if 'all_projects_history' in replit_db:
            projects_data = json.loads(replit_db['all_projects_history'])
            for proj in projects_data:
                try:
                    conn.execute('''
                        INSERT OR REPLACE INTO project_investments 
                        (id, user_id, project_id, amount, investment_date, transaction_hash)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (
                        proj.get('id'), proj.get('user_id'), proj.get('project_id'),
                        proj.get('amount'), proj.get('investment_date'), proj.get('transaction_hash')
                    ))
                except Exception as e:
                    print(f"⚠️ Erreur restauration projet {proj.get('id')}: {e}")
        
        # Restaurer TOUTES les transactions
        if 'all_transactions_history' in replit_db:
            transactions_data = json.loads(replit_db['all_transactions_history'])
            for trans in transactions_data:
                try:
                    conn.execute('''
                        INSERT OR REPLACE INTO transactions 
                        (id, user_id, type, amount, status, transaction_hash, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        trans.get('id'), trans.get('user_id'), trans.get('type'),
                        trans.get('amount'), trans.get('status'), trans.get('transaction_hash'),
                        trans.get('created_at'), trans.get('updated_at')
                    ))
                except Exception as e:
                    print(f"⚠️ Erreur restauration transaction {trans.get('id')}: {e}")
        
        # Restaurer les soldes utilisateurs
        if 'user_balances' in replit_db:
            users_data = json.loads(replit_db['user_balances'])
            for user in users_data:
                try:
                    conn.execute('''
                        UPDATE users SET balance = ? WHERE id = ?
                    ''', (user.get('balance', 0), user.get('id')))
                except Exception as e:
                    print(f"⚠️ Erreur restauration solde utilisateur {user.get('id')}: {e}")
        
        conn.commit()
        conn.close()
        
        last_backup = replit_db.get('last_backup', 'Inconnue')
        print(f"✅ Historique complet restauré depuis la sauvegarde du {last_backup}")
        return True
        
    except Exception as e:
        print(f"❌ Erreur restauration: {e}")
        return False

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

    # Auto Trading Strategies table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trading_strategies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            risk_level TEXT NOT NULL,
            expected_daily_return REAL NOT NULL,
            min_amount REAL NOT NULL,
            max_amount REAL NOT NULL,
            strategy_type TEXT NOT NULL,
            parameters TEXT NOT NULL,
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # User Trading Bots table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_trading_bots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            strategy_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            start_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            end_date TIMESTAMP,
            is_active BOOLEAN DEFAULT 1,
            total_profit REAL DEFAULT 0.0,
            daily_profit REAL DEFAULT 0.0,
            last_profit_date TIMESTAMP,
            transaction_hash TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (strategy_id) REFERENCES trading_strategies (id)
        )
    ''')

    # Top Traders table (pour copy trading)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS top_traders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            avatar_url TEXT,
            total_return REAL NOT NULL,
            win_rate REAL NOT NULL,
            followers_count INTEGER DEFAULT 0,
            monthly_return REAL NOT NULL,
            risk_score REAL NOT NULL,
            trading_style TEXT NOT NULL,
            min_copy_amount REAL NOT NULL,
            max_copy_amount REAL NOT NULL,
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # User Copy Trading table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_copy_trading (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            trader_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            start_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            end_date TIMESTAMP,
            is_active BOOLEAN DEFAULT 1,
            total_profit REAL DEFAULT 0.0,
            copy_ratio REAL DEFAULT 1.0,
            transaction_hash TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (trader_id) REFERENCES top_traders (id)
        )
    ''')

    # Trading Signals table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trading_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_id INTEGER NOT NULL,
            signal_type TEXT NOT NULL,
            asset_pair TEXT NOT NULL,
            action TEXT NOT NULL,
            price REAL NOT NULL,
            confidence REAL NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_executed BOOLEAN DEFAULT 0,
            FOREIGN KEY (strategy_id) REFERENCES trading_strategies (id)
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

    # Insert ultra-premium ROI plans (only if not exist)
    roi_count = cursor.execute('SELECT COUNT(*) as count FROM roi_plans').fetchone()['count']
    
    if roi_count == 0:
        cursor.execute('''
            INSERT INTO roi_plans (name, description, daily_rate, duration_days, min_amount, max_amount)
        VALUES 
        ('Turbo Flash', '🔥 Plan turbo flash ! 20% quotidien pendant 14 jours.', 0.20, 14, 20, 8000),
        ('Mega Profit', '💎 Plan mega profit ! 45% quotidien pendant 5 jours.', 0.45, 5, 50, 5000),
        ('Ultra Boost', '🚀 Plan ultra boost ! 75% quotidien pendant 2 jours.', 0.75, 2, 50, 3000)
    ''')

    # Insert top 10 staking plans - Starting from 20 USDT (only if not exist)
    staking_count = cursor.execute('SELECT COUNT(*) as count FROM staking_plans').fetchone()['count']
    
    if staking_count == 0:
        cursor.execute('''
            INSERT INTO staking_plans (name, description, duration_days, annual_rate, min_amount, max_amount, penalty_rate)
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

    # Quiz questions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS quiz_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            option_a TEXT NOT NULL,
            option_b TEXT NOT NULL,
            option_c TEXT NOT NULL,
            option_d TEXT NOT NULL,
            correct_answer TEXT NOT NULL,
            category TEXT DEFAULT 'crypto',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Quiz games table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS quiz_games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            bet_amount REAL NOT NULL,
            questions_answered INTEGER DEFAULT 0,
            correct_answers INTEGER DEFAULT 0,
            result TEXT,
            profit_loss REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # Insert quiz questions (only if not exist)
    quiz_count = cursor.execute('SELECT COUNT(*) as count FROM quiz_questions').fetchone()['count']
    
    if quiz_count == 0:
        cursor.execute('''
            INSERT INTO quiz_questions (question, option_a, option_b, option_c, option_d, correct_answer, category)
            VALUES 
            ('Quel est le créateur du Bitcoin ?', 'Vitalik Buterin', 'Satoshi Nakamoto', 'Elon Musk', 'Charlie Lee', 'B', 'crypto'),
            ('En quelle année le Bitcoin a-t-il été créé ?', '2007', '2009', '2011', '2013', 'B', 'crypto'),
            ('Quelle blockchain utilise Ethereum ?', 'Proof of Work', 'Proof of Stake', 'Proof of Authority', 'Delegated PoS', 'B', 'crypto'),
            ('Quel est le symbole du Bitcoin ?', 'ETH', 'BTC', 'LTC', 'XRP', 'B', 'crypto'),
            ('Combien de Bitcoin peuvent exister au maximum ?', '18 millions', '21 millions', '25 millions', 'Illimité', 'B', 'crypto'),
            ('Quest-ce quun wallet crypto ?', 'Un exchange', 'Un portefeuille numérique', 'Une banque', 'Un token', 'B', 'crypto'),
            ('Quel est le deuxième plus grand crypto par capitalisation ?', 'Ripple', 'Cardano', 'Ethereum', 'Solana', 'C', 'crypto'),
            ('Quest-ce que le halving du Bitcoin ?', 'Division par 2 de la récompense', 'Doublement du prix', 'Fermeture du réseau', 'Mise à jour logicielle', 'A', 'crypto'),
            ('Quelle crypto est connue pour les smart contracts ?', 'Bitcoin', 'Ethereum', 'Dogecoin', 'Litecoin', 'B', 'crypto'),
            ('Quest-ce quun NFT ?', 'Une crypto monnaie', 'Un token non-fongible', 'Un exchange', 'Un wallet', 'B', 'crypto'),
            ('Quel est le consensus utilisé par Bitcoin ?', 'Proof of Stake', 'Proof of Work', 'Proof of History', 'Proof of Burn', 'B', 'crypto'),
            ('Quest-ce que DeFi ?', 'Finance décentralisée', 'Digital Finance', 'Default Finance', 'Debt Finance', 'A', 'crypto'),
            ('Quelle crypto utilise le symbole SOL ?', 'Solana', 'Stellar', 'Cardano', 'Polkadot', 'A', 'crypto'),
            ('Quest-ce quun stablecoin ?', 'Crypto volatile', 'Crypto à prix stable', 'Crypto de jeu', 'Crypto privée', 'B', 'crypto'),
            ('Quel est le réseau Layer 2 populaire pour Ethereum ?', 'Polygon', 'Bitcoin', 'Cardano', 'Ripple', 'A', 'crypto'),
            ('Quest-ce que le gas sur Ethereum ?', 'Frais de transaction', 'Un token', 'Un wallet', 'Un exchange', 'A', 'crypto'),
            ('Combien de satoshis dans 1 Bitcoin ?', '1 million', '10 millions', '100 millions', '1 milliard', 'C', 'crypto'),
            ('Quest-ce quun airdrop en crypto ?', 'Distribution gratuite de tokens', 'Vente de tokens', 'Brûlage de tokens', 'Staking de tokens', 'A', 'crypto'),
            ('Quel animal est le logo de Dogecoin ?', 'Un chat', 'Un chien Shiba', 'Un lapin', 'Un ours', 'B', 'crypto'),
            ('Quest-ce que HODL ?', 'Hold On for Dear Life', 'High Order Digital Ledger', 'Hash Of Distributed Ledger', 'Hybrid Online Data Layer', 'A', 'crypto')
        ''')

    # Insert top 10 frozen plans - Starting from 20 USDT (only if not exist)
    frozen_count = cursor.execute('SELECT COUNT(*) as count FROM frozen_plans').fetchone()['count']
    
    if frozen_count == 0:
        cursor.execute('''
            INSERT INTO frozen_plans (name, description, duration_days, total_return_rate, min_amount, max_amount)
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

    # Insert top 10 projects - Starting from 20 USDT (only if not exist)
    projects_count = cursor.execute('SELECT COUNT(*) as count FROM projects').fetchone()['count']
    
    if projects_count == 0:
        cursor.execute('''
            INSERT INTO projects (title, description, category, target_amount, expected_return, duration_months, min_investment, max_investment, deadline)
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

    # Insert trading strategies (only if not exist)
    strategies_count = cursor.execute('SELECT COUNT(*) as count FROM trading_strategies').fetchone()['count']
    
    if strategies_count == 0:
        cursor.execute('''
            INSERT INTO trading_strategies (name, description, risk_level, expected_daily_return, min_amount, max_amount, strategy_type, parameters)
        VALUES 
        ('IA Conservateur', '🛡️ Stratégie IA sécurisée avec analyse de risque avancée. Idéale pour débuter le trading automatique.', 'Faible', 0.015, 20, 1000, 'ai_conservative', '{"stop_loss": 0.05, "take_profit": 0.03, "max_trades": 3}'),
        ('IA Équilibré', '⚖️ Stratégie IA équilibrée combinant sécurité et performance. Parfait équilibre risque/rendement.', 'Moyen', 0.025, 20, 2000, 'ai_balanced', '{"stop_loss": 0.08, "take_profit": 0.05, "max_trades": 5}'),
        ('IA Agressif', '🚀 Stratégie IA haute performance avec algorithmes avancés. Pour investisseurs expérimentés.', 'Élevé', 0.04, 20, 5000, 'ai_aggressive', '{"stop_loss": 0.12, "take_profit": 0.08, "max_trades": 8}'),
        ('Scalping Bot', '⚡ Bot de scalping ultra-rapide avec IA prédictive. Trades haute fréquence pour profits constants.', 'Moyen', 0.035, 20, 3000, 'scalping_ai', '{"timeframe": "1m", "trades_per_hour": 10, "profit_target": 0.02}'),
        ('Arbitrage IA', '🔄 Bot d arbitrage intelligent détectant les écarts de prix entre exchanges. Profits garantis.', 'Faible', 0.02, 20, 10000, 'arbitrage_ai', '{"min_spread": 0.01, "max_exposure": 0.3, "exchanges": 5}'),
        ('Swing Trading Pro', '📈 IA de swing trading analysant les tendances moyennes. Positions 2-7 jours pour profits optimaux.', 'Moyen', 0.03, 20, 4000, 'swing_ai', '{"timeframe": "4h", "trend_strength": 0.7, "position_size": 0.2}'),
        ('DeFi Yield Bot', '🌾 Bot DeFi intelligent optimisant les rendements sur protocols décentralisés. Farming automatisé.', 'Moyen', 0.045, 20, 8000, 'defi_yield', '{"protocols": ["uniswap", "compound"], "rebalance_frequency": "daily"}'),
        ('Grid Trading IA', '🔳 Stratégie de trading en grille avec IA adaptative. Profits dans tous les marchés.', 'Faible', 0.018, 20, 6000, 'grid_ai', '{"grid_size": 20, "price_range": 0.1, "adaptive": true}'),
        ('News Trading Bot', '📰 Bot réagissant aux news crypto en temps réel avec analyse sentiment IA. Profits sur volatilité.', 'Élevé', 0.038, 20, 2500, 'news_ai', '{"sentiment_threshold": 0.8, "reaction_time": "30s", "news_sources": 15}'),
        ('Multi-Strategy IA', '🎯 Bot combinant plusieurs stratégies IA adaptatives. Performance optimisée automatiquement.', 'Moyen', 0.032, 20, 15000, 'multi_ai', '{"strategies": 5, "allocation_dynamic": true, "rebalance": "weekly"}')
    ''')

    # Insert top traders for copy trading (only if not exist)
    traders_count = cursor.execute('SELECT COUNT(*) as count FROM top_traders').fetchone()['count']
    
    if traders_count == 0:
        cursor.execute('''
            INSERT INTO top_traders (name, avatar_url, total_return, win_rate, followers_count, monthly_return, risk_score, trading_style, min_copy_amount, max_copy_amount)
        VALUES 
        ('CryptoKing_AI', '/static/avatars/trader1.png', 245.5, 78.5, 1250, 25.2, 6.2, 'Swing Trading + IA', 20, 5000),
        ('QuantMaster_Pro', '/static/avatars/trader2.png', 189.3, 82.1, 980, 18.7, 4.8, 'Algorithmic Trading', 20, 3000),
        ('ScalpBot_Elite', '/static/avatars/trader3.png', 156.8, 75.3, 1580, 22.4, 7.1, 'Scalping + Arbitrage', 20, 2500),
        ('TrendHunter_IA', '/static/avatars/trader4.png', 198.7, 80.2, 920, 19.8, 5.5, 'Trend Following IA', 20, 4000),
        ('DeFi_Wizard', '/static/avatars/trader5.png', 134.2, 88.9, 750, 15.8, 3.2, 'DeFi Yield Farming', 20, 8000),
        ('Volatility_Pro', '/static/avatars/trader6.png', 178.5, 73.4, 1120, 21.3, 8.5, 'Volatility Trading', 20, 3500),
        ('AI_GridMaster', '/static/avatars/trader7.png', 145.6, 85.7, 680, 16.9, 4.1, 'Grid + IA Adaptive', 20, 6000),
        ('NewsBot_Elite', '/static/avatars/trader8.png', 167.3, 76.8, 1340, 20.1, 6.8, 'News-based Trading', 20, 2800),
        ('Hodl_IA_Pro', '/static/avatars/trader9.png', 123.8, 91.2, 2100, 14.5, 2.9, 'Long-term IA', 20, 10000),
        ('MultiStrat_Bot', '/static/avatars/trader10.png', 201.4, 79.6, 1450, 23.7, 5.9, 'Multi-Strategy IA', 20, 7500)
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
    # Sauvegarder les données importantes si Replit DB est disponible
    if REPLIT_DB_AVAILABLE:
        backup_critical_data()
    
    conn = get_db_connection()
    
    # Plus d'investissements ROI actifs
    active_investments = []

    # Récupérer tous les bots de trading actifs
    active_bots = conn.execute('''
        SELECT utb.*, u.email, ts.name as strategy_name
        FROM user_trading_bots utb
        JOIN users u ON utb.user_id = u.id
        JOIN trading_strategies ts ON utb.strategy_id = ts.id
        WHERE utb.is_active = 1
    ''').fetchall()

    # Récupérer tous les copy trades actifs
    active_copies = conn.execute('''
        SELECT uct.*, u.email, tt.name as trader_name, tt.monthly_return
        FROM user_copy_trading uct
        JOIN users u ON uct.user_id = u.id
        JOIN top_traders tt ON uct.trader_id = tt.id
        WHERE uct.is_active = 1
    ''').fetchall()

    print(f"🔄 Calcul des profits pour {len(active_investments)} investissements, {len(active_bots)} bots, {len(active_copies)} copy trades")

    # Traiter les investissements ROI classiques
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

    # Traiter les bots de trading
    for bot in active_bots:
        try:
            daily_profit = bot['daily_profit']
            
            if daily_profit > 0:
                print(f"🤖 Ajout de {daily_profit:.2f} USDT pour le bot {bot['id']} de l'utilisateur {bot['user_id']}")

                # Mettre à jour le solde utilisateur
                conn.execute('''
                    UPDATE users 
                    SET balance = balance + ? 
                    WHERE id = ?
                ''', (daily_profit, bot['user_id']))

                # Mettre à jour les profits totaux du bot
                current_profit = bot.get('total_profit', 0) or 0
                new_total_profit = current_profit + daily_profit
                conn.execute('''
                    UPDATE user_trading_bots 
                    SET total_profit = ?, last_profit_date = CURRENT_TIMESTAMP 
                    WHERE id = ?
                ''', (new_total_profit, bot['id']))

                # Ajouter transaction
                conn.execute('''
                    INSERT INTO transactions (user_id, type, amount, status, transaction_hash)
                    VALUES (?, 'bot_profit', ?, 'completed', ?)
                ''', (bot['user_id'], daily_profit, generate_transaction_hash()))

                # Ajouter notification
                add_notification(
                    bot['user_id'],
                    'Profit bot de trading',
                    f'Votre bot {bot["strategy_name"]} a généré {daily_profit:.2f} USDT de profit!',
                    'success'
                )

        except Exception as e:
            print(f"❌ Erreur calcul profit pour bot {bot['id']}: {e}")
            continue

    # Traiter les copy trades
    for copy_trade in active_copies:
        try:
            # Calculer le profit basé sur le rendement mensuel du trader
            monthly_return = copy_trade['monthly_return'] / 100  # Convertir en décimal
            daily_return = monthly_return / 30  # Approximation quotidienne
            daily_profit = copy_trade['amount'] * daily_return * copy_trade['copy_ratio']
            
            if daily_profit > 0:
                print(f"📈 Ajout de {daily_profit:.2f} USDT pour le copy trade {copy_trade['id']} de l'utilisateur {copy_trade['user_id']}")

                # Mettre à jour le solde utilisateur
                conn.execute('''
                    UPDATE users 
                    SET balance = balance + ? 
                    WHERE id = ?
                ''', (daily_profit, copy_trade['user_id']))

                # Mettre à jour les profits totaux du copy trade
                current_profit = copy_trade.get('total_profit', 0) or 0
                new_total_profit = current_profit + daily_profit
                conn.execute('''
                    UPDATE user_copy_trading 
                    SET total_profit = ? 
                    WHERE id = ?
                ''', (new_total_profit, copy_trade['id']))

                # Ajouter transaction
                conn.execute('''
                    INSERT INTO transactions (user_id, type, amount, status, transaction_hash)
                    VALUES (?, 'copy_profit', ?, 'completed', ?)
                ''', (copy_trade['user_id'], daily_profit, generate_transaction_hash()))

                # Ajouter notification
                add_notification(
                    copy_trade['user_id'],
                    'Profit copy trading',
                    f'Votre copy de {copy_trade["trader_name"]} a généré {daily_profit:.2f} USDT de profit!',
                    'success'
                )

        except Exception as e:
            print(f"❌ Erreur calcul profit pour copy trade {copy_trade['id']}: {e}")
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
                'admin@ttrust.com',
                'support@ttrust.com',
                'security@ttrust.com',
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

    # Get active investments (sans les plans ROI)
    investments = []

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

@app.route('/invest-roi', methods=['POST'])
@login_required
def invest_roi():
    """Investir dans un plan ROI ultra-rentable"""
    data = request.get_json()
    plan_id = data.get('plan_id')
    amount = float(data.get('amount', 0))

    conn = get_db_connection()

    # Récupérer les détails du plan
    plan = conn.execute('SELECT * FROM roi_plans WHERE id = ?', (plan_id,)).fetchone()
    if not plan:
        conn.close()
        return jsonify({'error': 'Plan non trouvé'}), 404

    # Vérifier les limites de montant
    if amount < plan['min_amount'] or amount > plan['max_amount']:
        conn.close()
        return jsonify({'error': f'Montant doit être entre {plan["min_amount"]} et {plan["max_amount"]} USDT'}), 400

    # Vérifier le solde utilisateur
    user = conn.execute('SELECT balance FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    if user['balance'] < amount:
        conn.close()
        return jsonify({'error': 'Solde insuffisant'}), 400

    # Calculer les dates et profits
    start_date = datetime.now()
    end_date = start_date + timedelta(days=plan['duration_days'])
    daily_profit = amount * plan['daily_rate']

    # Créer l'investissement
    cursor = conn.execute('''
        INSERT INTO user_investments (user_id, plan_id, amount, start_date, end_date, daily_profit, transaction_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (session['user_id'], plan_id, amount, start_date, end_date, daily_profit, generate_transaction_hash()))

    # Mettre à jour le solde utilisateur
    conn.execute('UPDATE users SET balance = balance - ? WHERE id = ?', (amount, session['user_id']))

    # Ajouter transaction
    conn.execute('''
        INSERT INTO transactions (user_id, type, amount, status, transaction_hash)
        VALUES (?, 'roi_investment', ?, 'completed', ?)
    ''', (session['user_id'], amount, generate_transaction_hash()))

    conn.commit()
    conn.close()

    # Ajouter notification
    add_notification(
        session['user_id'],
        'Investissement premium activé',
        f'Votre investissement de {amount} USDT dans {plan["name"]} a été activé avec succès!',
        'success'
    )

    return jsonify({'success': True, 'message': f'Investissement dans {plan["name"]} réalisé avec succès!'})

# ==================== QUIZ GAME ROUTES ====================

@app.route('/quiz-game')
@login_required
def quiz_game():
    """Page du jeu quiz avec mise"""
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    
    # Récupérer l'historique des parties
    quiz_history = conn.execute('''
        SELECT * FROM quiz_games 
        WHERE user_id = ? 
        ORDER BY created_at DESC 
        LIMIT 10
    ''', (session['user_id'],)).fetchall()
    
    conn.close()
    return render_template('quiz_game.html', user=user, quiz_history=quiz_history)

@app.route('/start-quiz', methods=['POST'])
@login_required
def start_quiz():
    """Démarrer une partie de quiz"""
    import random
    
    data = request.get_json()
    bet_amount = float(data.get('amount', 0))
    
    if bet_amount < 10:
        return jsonify({'error': 'Mise minimum: 10 USDT'}), 400
    
    conn = get_db_connection()
    
    # Vérifier le solde
    user = conn.execute('SELECT balance FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    if user['balance'] < bet_amount:
        conn.close()
        return jsonify({'error': 'Solde insuffisant'}), 400
    
    # Déduire la mise
    conn.execute('UPDATE users SET balance = balance - ? WHERE id = ?', (bet_amount, session['user_id']))
    
    # Créer la partie
    cursor = conn.execute('''
        INSERT INTO quiz_games (user_id, bet_amount)
        VALUES (?, ?)
    ''', (session['user_id'], bet_amount))
    game_id = cursor.lastrowid
    
    # Sélectionner 2 questions aléatoires
    questions = conn.execute('SELECT * FROM quiz_questions ORDER BY RANDOM() LIMIT 2').fetchall()
    
    conn.commit()
    conn.close()
    
    # Stocker les questions dans la session
    session['quiz_game_id'] = game_id
    session['quiz_questions'] = [dict(q) for q in questions]
    session['quiz_current'] = 0
    session['quiz_correct'] = 0
    session['quiz_bet'] = bet_amount
    
    return jsonify({
        'success': True,
        'game_id': game_id,
        'question': {
            'id': questions[0]['id'],
            'question': questions[0]['question'],
            'options': {
                'A': questions[0]['option_a'],
                'B': questions[0]['option_b'],
                'C': questions[0]['option_c'],
                'D': questions[0]['option_d']
            }
        },
        'question_number': 1,
        'total_questions': 2,
        'time_limit': 10
    })

@app.route('/submit-quiz-answer', methods=['POST'])
@login_required
def submit_quiz_answer():
    """Soumettre une réponse au quiz"""
    data = request.get_json()
    answer = data.get('answer', '').upper()
    time_taken = float(data.get('time_taken', 11))
    
    if 'quiz_game_id' not in session:
        return jsonify({'error': 'Aucune partie en cours'}), 400
    
    current_index = session.get('quiz_current', 0)
    questions = session.get('quiz_questions', [])
    
    if current_index >= len(questions):
        return jsonify({'error': 'Quiz terminé'}), 400
    
    current_question = questions[current_index]
    correct_answer = current_question['correct_answer']
    
    # Vérifier si le temps est écoulé (10 secondes)
    is_correct = False
    if time_taken <= 10 and answer == correct_answer:
        is_correct = True
        session['quiz_correct'] = session.get('quiz_correct', 0) + 1
    
    session['quiz_current'] = current_index + 1
    
    # Vérifier s'il reste des questions
    if session['quiz_current'] < len(questions):
        next_question = questions[session['quiz_current']]
        return jsonify({
            'success': True,
            'is_correct': is_correct,
            'correct_answer': correct_answer,
            'next_question': {
                'id': next_question['id'],
                'question': next_question['question'],
                'options': {
                    'A': next_question['option_a'],
                    'B': next_question['option_b'],
                    'C': next_question['option_c'],
                    'D': next_question['option_d']
                }
            },
            'question_number': session['quiz_current'] + 1,
            'total_questions': 2,
            'time_limit': 10
        })
    else:
        # Quiz terminé - calculer le résultat
        return complete_quiz_game()

def complete_quiz_game():
    """Compléter la partie et calculer les gains/pertes"""
    game_id = session.get('quiz_game_id')
    bet_amount = session.get('quiz_bet', 0)
    correct_answers = session.get('quiz_correct', 0)
    
    conn = get_db_connection()
    
    # 2 bonnes réponses = victoire (96% profit)
    # Sinon = perte (50% de la mise)
    if correct_answers == 2:
        result = 'win'
        profit = bet_amount * 0.96
        total_return = bet_amount + profit
        # Rendre la mise + profit
        conn.execute('UPDATE users SET balance = balance + ? WHERE id = ?', (total_return, session['user_id']))
    else:
        result = 'lose'
        profit = -(bet_amount * 0.50)
        # Rendre 50% de la mise
        refund = bet_amount * 0.50
        conn.execute('UPDATE users SET balance = balance + ? WHERE id = ?', (refund, session['user_id']))
    
    # Mettre à jour la partie
    conn.execute('''
        UPDATE quiz_games 
        SET questions_answered = 2, correct_answers = ?, result = ?, profit_loss = ?, completed_at = ?
        WHERE id = ?
    ''', (correct_answers, result, profit, datetime.now(), game_id))
    
    # Ajouter une transaction
    trans_type = 'quiz_win' if result == 'win' else 'quiz_loss'
    conn.execute('''
        INSERT INTO transactions (user_id, type, amount, status, transaction_hash)
        VALUES (?, ?, ?, 'completed', ?)
    ''', (session['user_id'], trans_type, abs(profit), generate_transaction_hash()))
    
    # Récupérer le nouveau solde
    user = conn.execute('SELECT balance FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    
    conn.commit()
    conn.close()
    
    # Nettoyer la session
    session.pop('quiz_game_id', None)
    session.pop('quiz_questions', None)
    session.pop('quiz_current', None)
    session.pop('quiz_correct', None)
    session.pop('quiz_bet', None)
    
    # Ajouter notification
    if result == 'win':
        add_notification(
            session['user_id'],
            'Quiz Gagné! 🎉',
            f'Bravo! Vous avez gagné {profit:.2f} USDT avec le quiz!',
            'success'
        )
    else:
        add_notification(
            session['user_id'],
            'Quiz Perdu',
            f'Dommage! Vous avez perdu {abs(profit):.2f} USDT. 50% de votre mise a été remboursé.',
            'warning'
        )
    
    return jsonify({
        'success': True,
        'game_complete': True,
        'result': result,
        'correct_answers': correct_answers,
        'profit_loss': profit,
        'new_balance': user['balance']
    })

@app.route('/timeout-quiz', methods=['POST'])
@login_required
def timeout_quiz():
    """Gérer le timeout d'une question"""
    if 'quiz_game_id' not in session:
        return jsonify({'error': 'Aucune partie en cours'}), 400
    
    # Marquer comme mauvaise réponse et passer à la suivante
    return submit_quiz_answer()

# ==================== END QUIZ GAME ROUTES ====================

@app.route('/investment-history')
@login_required
def investment_history():
    """Page d'historique complet des investissements"""
    conn = get_db_connection()

    # Récupérer tous les investissements ROI de l'utilisateur
    roi_investments = conn.execute('''
        SELECT ui.*, rp.name as plan_name
        FROM user_investments ui
        LEFT JOIN roi_plans rp ON ui.plan_id = rp.id
        WHERE ui.user_id = ?
        ORDER BY ui.start_date DESC
    ''', (session['user_id'],)).fetchall()

    # Récupérer tous les investissements staking
    staking_investments = conn.execute('''
        SELECT us.*, sp.name as plan_name, sp.duration_days, sp.annual_rate
        FROM user_staking us
        LEFT JOIN staking_plans sp ON us.plan_id = sp.id
        WHERE us.user_id = ?
        ORDER BY us.start_date DESC
    ''', (session['user_id'],)).fetchall()

    # Récupérer tous les bots de trading
    trading_bots = conn.execute('''
        SELECT utb.*, ts.name as strategy_name, ts.risk_level
        FROM user_trading_bots utb
        LEFT JOIN trading_strategies ts ON utb.strategy_id = ts.id
        WHERE utb.user_id = ?
        ORDER BY utb.start_date DESC
    ''', (session['user_id'],)).fetchall()

    # Récupérer tous les copy trades
    copy_trades = conn.execute('''
        SELECT uct.*, tt.name as trader_name, tt.total_return
        FROM user_copy_trading uct
        LEFT JOIN top_traders tt ON uct.trader_id = tt.id
        WHERE uct.user_id = ?
        ORDER BY uct.start_date DESC
    ''', (session['user_id'],)).fetchall()

    # Récupérer les investissements dans les projets
    project_investments = conn.execute('''
        SELECT pi.*, p.title, p.status, p.expected_return
        FROM project_investments pi
        JOIN projects p ON pi.project_id = p.id
        WHERE pi.user_id = ?
        ORDER BY pi.investment_date DESC
    ''', (session['user_id'],)).fetchall()

    conn.close()

    # Calculer les statistiques globales
    total_invested = 0
    total_profits = 0
    active_count = 0
    completed_count = 0

    # Traiter les investissements ROI
    for inv in roi_investments:
        total_invested += inv['amount'] if inv['amount'] else 0
        total_profits += inv['total_earned'] if inv['total_earned'] else 0
        if inv['is_active']:
            active_count += 1
        else:
            completed_count += 1

    # Traiter les investissements staking
    for inv in staking_investments:
        total_invested += inv['amount'] if inv['amount'] else 0
        total_profits += inv['total_earned'] if inv['total_earned'] else 0
        if inv['is_active']:
            active_count += 1
        else:
            completed_count += 1

    # Traiter les bots de trading
    for bot in trading_bots:
        total_invested += bot['amount'] if bot['amount'] else 0
        total_profits += bot['total_profit'] if bot['total_profit'] else 0
        if bot['is_active']:
            active_count += 1
        else:
            completed_count += 1

    # Traiter les copy trades
    for trade in copy_trades:
        total_invested += trade['amount'] if trade['amount'] else 0
        total_profits += trade['total_profit'] if trade['total_profit'] else 0
        if trade['is_active']:
            active_count += 1
        else:
            completed_count += 1

    # Traiter les investissements projets
    for proj in project_investments:
        total_invested += proj['amount'] if proj['amount'] else 0
        # Les projets sont considérés comme actifs
        active_count += 1

    # Créer un dictionnaire de statistiques
    stats = {
        'total_invested': total_invested,
        'total_profits': total_profits,
        'active_count': active_count,
        'completed_count': completed_count,
        'total_count': len(roi_investments) + len(staking_investments) + len(trading_bots) + len(copy_trades) + len(project_investments)
    }

    # Combiner tous les investissements pour les filtres
    all_investments = []
    
    # Ajouter les investissements ROI
    for inv in roi_investments:
        all_investments.append({
            'id': inv['id'],
            'type': 'roi',
            'amount': inv['amount'],
            'total_earned': inv['total_earned'] if inv['total_earned'] else 0,
            'is_active': inv['is_active'],
            'start_date': inv['start_date']
        })
    
    # Ajouter les autres types d'investissements
    for inv in staking_investments:
        all_investments.append({
            'id': inv['id'],
            'type': 'staking',
            'amount': inv['amount'],
            'total_earned': inv['total_earned'] if inv['total_earned'] else 0,
            'is_active': inv['is_active'],
            'start_date': inv['start_date']
        })
    
    for bot in trading_bots:
        all_investments.append({
            'id': bot['id'],
            'type': 'trading',
            'amount': bot['amount'],
            'total_earned': bot['total_profit'] if bot['total_profit'] else 0,
            'is_active': bot['is_active'],
            'start_date': bot['start_date']
        })
    
    for trade in copy_trades:
        all_investments.append({
            'id': trade['id'],
            'type': 'copy',
            'amount': trade['amount'],
            'total_earned': trade['total_profit'] if trade['total_profit'] else 0,
            'is_active': trade['is_active'],
            'start_date': trade['start_date']
        })
    
    for proj in project_investments:
        all_investments.append({
            'id': proj['id'],
            'type': 'project',
            'amount': proj['amount'],
            'total_earned': 0,  # Les projets n'ont pas encore de gains
            'is_active': True,
            'start_date': proj['investment_date']
        })

    return render_template('investment_history.html',
                         roi_investments=roi_investments,
                         staking_investments=staking_investments,
                         trading_bots=trading_bots,
                         copy_trades=copy_trades,
                         project_investments=project_investments,
                         all_investments=all_investments,
                         stats=stats)

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
        'AAAA'
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

@app.route('/restore-from-backup', methods=['POST'])
@login_required
def restore_from_backup():
    """Restaurer manuellement depuis la sauvegarde"""
    try:
        if not REPLIT_DB_AVAILABLE:
            return jsonify({
                'error': 'Sauvegarde Replit non disponible'
            }), 400
        
        success = restore_critical_data()
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Données restaurées depuis la sauvegarde!'
            })
        else:
            return jsonify({
                'error': 'Aucune sauvegarde disponible ou données déjà présentes'
            }), 400
            
    except Exception as e:
        return jsonify({
            'error': f'Erreur: {str(e)}'
        }), 500

@app.route('/force-backup', methods=['POST'])
@login_required
def force_backup():
    """Forcer une sauvegarde manuelle"""
    try:
        if not REPLIT_DB_AVAILABLE:
            return jsonify({
                'error': 'Sauvegarde Replit non disponible'
            }), 400
        
        backup_critical_data()
        
        return jsonify({
            'success': True,
            'message': 'Sauvegarde effectuée avec succès!'
        })
            
    except Exception as e:
        return jsonify({
            'error': f'Erreur: {str(e)}'
        }), 500


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
            issuer_name="Ttrust"
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
            
            # Tenter de restaurer les données depuis la sauvegarde
            if REPLIT_DB_AVAILABLE:
                restore_critical_data()
            
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
    create_secure_admin('admin@ttrust.com', 'AAAA', 'Admin', 'Principal')
    create_secure_admin('support@ttrust.com', 'AAAA', 'Support', 'Team')
    create_secure_admin('security@ttrust.com', 'AAAA', 'Security', 'Team')
    create_secure_admin('a@gmail.com', 'AAAA', 'Admin', 'User')

    # Mettre à jour le mot de passe du compte a@gmail.com
    update_admin_password('a@gmail.com', 'AAAA')

    # Setup scheduler for daily profit calculation and backup
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=calculate_daily_profits,
        trigger="cron",
        hour=0,
        minute=0,
        id='daily_profits'
    )
    
    # Sauvegarde périodique toutes les 30 minutes si Replit DB disponible
    if REPLIT_DB_AVAILABLE:
        scheduler.add_job(
            func=backup_critical_data,
            trigger="interval",
            minutes=30,
            id='backup_data'
        )
    
    scheduler.start()

    # Shutdown scheduler when exiting the app
    atexit.register(lambda: scheduler.shutdown())

    app.run(host='0.0.0.0', port=5000, debug=True)