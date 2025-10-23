# Plateforme d'Investissement Ttrust

## 📋 Description
Plateforme d'investissement complète offrant plusieurs types d'opportunités d'investissement avec un système de gestion utilisateur avancé, authentification 2FA, et support client intégré.

## ✨ Fonctionnalités Principales

### Investissements
- **Plans ROI** : Plans d'investissement avec rendement fixe
- **Staking** : Programmes de staking crypto
- **Plans Frozen** : Investissements à long terme
- **Plans Ultra** : Investissements premium à haut rendement
- **Crowdfunding** : Projets participatifs
- **Auto Trading** : Trading automatisé par IA
- **Copy Trading** : Copie des meilleurs traders

### Sécurité
- Authentification à deux facteurs (2FA) avec Google Authenticator
- Gestion des sessions sécurisées
- Protection contre les tentatives de connexion multiples
- Hachage sécurisé des mots de passe

### Administration
- Dashboard administrateur complet
- Gestion des utilisateurs et KYC
- Validation des transactions
- Système de support ticket
- Rapports et statistiques

### Utilisateur
- Dashboard personnalisé
- Historique des investissements
- Profil et paramètres de sécurité
- Notifications en temps réel
- Support client intégré

## 🚀 Technologies Utilisées
- **Backend** : Flask (Python)
- **Base de données** : SQLite
- **Authentification** : PyOTP, Werkzeug
- **Tâches planifiées** : APScheduler
- **Interface** : Templates HTML/CSS
- **PWA** : Service Workers pour fonctionnalité offline

## 📦 Dépendances
```
flask>=3.1.1
werkzeug>=3.1.3
apscheduler>=3.11.0
pyotp>=2.9.0
qrcode[pil]>=8.2
python-telegram-bot[webhooks]==20.7
telegram>=0.0.1
```

## ⚙️ Installation et Lancement

### Installation des dépendances
```bash
pip install -r requirements.txt
```

### Lancement de l'application
```bash
python main.py
```

L'application sera accessible sur `http://0.0.0.0:5000`

## 👤 Comptes Administrateur par Défaut

Par sécurité, plusieurs comptes admin sont créés automatiquement :

1. **Admin Principal**
   - Email : `admin@ttrust.com`
   - Mot de passe : `AdminSecure2024!`

2. **Support**
   - Email : `support@ttrust.com`
   - Mot de passe : `SupportSecure2024!`

3. **Sécurité**
   - Email : `security@ttrust.com`
   - Mot de passe : `SecuritySecure2024!`

4. **Test**
   - Email : `a@gmail.com`
   - Mot de passe : `aaaaaa`

⚠️ **Important** : Changez ces mots de passe après le premier déploiement en production !

## 📁 Structure du Projet

```
.
├── main.py                    # Fichier principal Flask
├── investment_platform.db     # Base de données SQLite
├── pyproject.toml            # Configuration projet Python
├── requirements.txt          # Dépendances pip
├── static/                   # Fichiers statiques
│   ├── icons/               # Icônes PWA
│   ├── manifest.json        # Manifest PWA
│   ├── sw.js               # Service Worker
│   └── offline.html        # Page offline
├── templates/               # Templates HTML
│   ├── base.html           # Template de base
│   ├── dashboard.html      # Dashboard utilisateur
│   ├── admin_*.html        # Pages admin
│   └── *.html             # Autres pages
└── uploads/                # Fichiers uploadés
```

## 🔄 Tâches Automatiques

L'application configure automatiquement :
- **Calcul des profits quotidiens** : Tous les jours à minuit
- **Sauvegarde des données** : Toutes les 30 minutes (si Replit DB disponible)

## 🌐 Progressive Web App (PWA)

L'application est une PWA et peut être installée sur les appareils mobiles et desktop pour une expérience native.

## 📊 Base de Données

La base de données SQLite contient les tables suivantes :
- `users` : Utilisateurs et leurs informations
- `user_investments` : Investissements ROI
- `projects` : Projets de crowdfunding
- `project_investments` : Investissements dans les projets
- `transactions` : Historique des transactions
- `support_tickets` : Tickets de support
- `notifications` : Notifications utilisateur
- Et plusieurs autres tables pour les différents types d'investissements

## 🔐 Sécurité

- Mots de passe hachés avec Werkzeug
- Protection CSRF
- Sessions sécurisées
- Authentification 2FA disponible
- Verrouillage de compte après échecs de connexion
- Validation des données côté serveur

## 📝 Notes de Développement

- Le mode debug est activé par défaut (à désactiver en production)
- La base de données est initialisée automatiquement au démarrage
- Les fichiers uploadés sont stockés dans le dossier `uploads/`
- Les logs s'affichent dans la console

## 🚢 Déploiement

Pour déployer en production :

1. Désactiver le mode debug dans `main.py` :
   ```python
   app.run(host='0.0.0.0', port=5000, debug=False)
   ```

2. Utiliser un serveur WSGI comme Gunicorn :
   ```bash
   gunicorn --bind 0.0.0.0:5000 main:app
   ```

3. Changer tous les mots de passe admin par défaut

4. Configurer les variables d'environnement pour les secrets

## ⚠️ Avertissements

- Ceci est une plateforme d'investissement. Assurez-vous de respecter toutes les réglementations financières locales.
- En production, utilisez HTTPS uniquement.
- Effectuez des sauvegardes régulières de la base de données.
- Testez toutes les fonctionnalités avant mise en production.

## 📞 Support

Le système de support est intégré dans l'application avec un système de tickets.

---

**Version** : 0.1.0  
**Dernière mise à jour** : 2025  
**Statut** : Prêt pour déploiement
