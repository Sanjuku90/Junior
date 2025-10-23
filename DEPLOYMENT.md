# 🚀 Guide de Déploiement

## Déploiement sur Replit

### Étapes
1. Ouvrez votre projet sur Replit
2. Le workflow est déjà configuré pour démarrer automatiquement
3. Cliquez sur "Run" - l'application démarrera sur le port 5000
4. Utilisez le bouton "Webview" pour voir l'application

### Configuration Production
Avant de publier en production :

1. **Désactiver le mode debug** dans `main.py` :
```python
app.run(host='0.0.0.0', port=5000, debug=False)
```

2. **Changer les mots de passe admin** :
   - Connectez-vous avec `a@gmail.com` / `aaaaaa`
   - Allez dans les paramètres admin
   - Modifiez tous les mots de passe par défaut

3. **Configurer les sauvegardes** :
   - La base de données SQLite est sauvegardée automatiquement
   - Téléchargez régulièrement `investment_platform.db`

## Déploiement sur Cursor

### Étapes
1. Clonez ou ouvrez le projet dans Cursor
2. Installez les dépendances :
```bash
pip install -r requirements.txt
```

3. Lancez l'application :
```bash
python main.py
```

4. Accédez à `http://localhost:5000`

## Déploiement avec Gunicorn (Production)

### Installation
```bash
pip install gunicorn
```

### Lancement
```bash
gunicorn --workers 4 --bind 0.0.0.0:5000 main:app
```

### Avec systemd (Linux)
Créez `/etc/systemd/system/ttrust.service` :

```ini
[Unit]
Description=Ttrust Investment Platform
After=network.target

[Service]
User=www-data
WorkingDirectory=/chemin/vers/projet
Environment="PATH=/chemin/vers/venv/bin"
ExecStart=/chemin/vers/venv/bin/gunicorn --workers 4 --bind 0.0.0.0:5000 main:app
Restart=always

[Install]
WantedBy=multi-user.target
```

Activez et démarrez :
```bash
sudo systemctl enable ttrust
sudo systemctl start ttrust
```

## Déploiement avec Docker

### Créer Dockerfile
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["gunicorn", "--workers", "4", "--bind", "0.0.0.0:5000", "main:app"]
```

### Build et Run
```bash
docker build -t ttrust-platform .
docker run -d -p 5000:5000 -v $(pwd)/investment_platform.db:/app/investment_platform.db ttrust-platform
```

## Configuration Nginx (Reverse Proxy)

```nginx
server {
    listen 80;
    server_name votre-domaine.com;

    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static {
        alias /chemin/vers/projet/static;
        expires 30d;
    }
}
```

## Variables d'Environnement

Copiez `.env.example` vers `.env` et configurez :

```bash
cp .env.example .env
nano .env
```

## Sauvegardes

### Backup manuel
```bash
sqlite3 investment_platform.db .dump > backup_$(date +%Y%m%d).sql
```

### Backup automatique (cron)
```bash
0 2 * * * sqlite3 /chemin/vers/investment_platform.db .dump > /chemin/sauvegardes/backup_$(date +\%Y\%m\%d).sql
```

## SSL/HTTPS

### Avec Certbot (Let's Encrypt)
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d votre-domaine.com
```

## Monitoring

### Logs Application
```bash
tail -f /var/log/ttrust/app.log
```

### Logs Nginx
```bash
tail -f /var/log/nginx/access.log
tail -f /var/log/nginx/error.log
```

## Performance

### Optimisations recommandées
- Utilisez Redis pour les sessions (optionnel)
- Activez le caching Nginx
- Configurez gzip dans Nginx
- Utilisez CDN pour les fichiers statiques

## Sécurité Production

### Checklist
- [ ] Mode debug désactivé
- [ ] Tous les mots de passe admin changés
- [ ] HTTPS activé
- [ ] Firewall configuré
- [ ] Sauvegardes automatiques activées
- [ ] Monitoring mis en place
- [ ] Logs rotationnés
- [ ] Rate limiting configuré
- [ ] CORS configuré si nécessaire

## Mise à jour

```bash
# Arrêter l'application
sudo systemctl stop ttrust

# Backup base de données
sqlite3 investment_platform.db .dump > backup_pre_update.sql

# Mettre à jour le code
git pull origin main

# Installer nouvelles dépendances
pip install -r requirements.txt

# Redémarrer
sudo systemctl start ttrust
```

## Troubleshooting

### Application ne démarre pas
```bash
# Vérifier les logs
journalctl -u ttrust -n 50

# Vérifier le port
netstat -tulpn | grep 5000
```

### Base de données verrouillée
```bash
# Identifier les processus utilisant la DB
lsof | grep investment_platform.db

# Redémarrer l'application
sudo systemctl restart ttrust
```

## Support

En cas de problème :
1. Vérifiez les logs
2. Consultez la documentation dans `replit.md`
3. Vérifiez la configuration dans `.env`

---

**Note** : Ce guide couvre plusieurs méthodes de déploiement. Choisissez celle qui convient le mieux à vos besoins.
