# 🚀 Guide de Déploiement sur Render

## ✅ Fichiers préparés

Votre projet est maintenant **prêt pour Render** avec :
- ✅ `requirements.txt` mis à jour (avec Gunicorn)
- ✅ `render.yaml` créé (configuration automatique)
- ✅ Application Flask optimisée

## 📝 Étapes de déploiement

### 1. Créer un compte Render
- Allez sur **https://dashboard.render.com/register**
- Inscrivez-vous (gratuit, pas de carte bancaire nécessaire)
- Connectez votre compte **GitHub**

### 2. Déployer votre application

#### Option A : Déploiement automatique (RECOMMANDÉ)

1. **Allez sur** https://dashboard.render.com
2. **Cliquez sur** "New +" → "Web Service"
3. **Sélectionnez** votre dépôt GitHub `Sanjuku90/Byygy`
4. **Render détecte automatiquement** le fichier `render.yaml`
5. **Cliquez sur** "Apply"

✨ C'est tout ! Render va :
- Installer les dépendances
- Démarrer votre application avec Gunicorn
- Vous donner une URL : `https://ttrust-platform.onrender.com`

#### Option B : Configuration manuelle

Si vous préférez configurer manuellement :

1. **New +" → "Web Service**
2. **Sélectionnez** votre dépôt
3. **Remplissez** :

| Champ | Valeur |
|-------|--------|
| Name | `ttrust-platform` |
| Region | Oregon (ou autre) |
| Branch | `main` |
| Runtime | Python 3 |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `gunicorn main:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120` |

4. **Variables d'environnement** (Advanced) :
   - `PYTHON_VERSION` = `3.11`
   - `FLASK_ENV` = `production`

5. **Sélectionnez** le plan **Free**
6. **Cliquez** sur "Create Web Service"

### 3. Surveillance du déploiement

- Render va cloner votre code GitHub
- Installer les dépendances (2-3 minutes)
- Démarrer l'application
- Consultez les **Logs** en temps réel

### 4. Votre application est en ligne ! 🎉

Vous recevrez une URL comme :
```
https://ttrust-platform.onrender.com
```

## ⚠️ Important pour la production

### 1. Désactiver le mode debug

Dans `main.py`, ligne 3445, changez :
```python
app.run(host='0.0.0.0', port=5000, debug=False)  # debug=False !
```

### 2. Base de données persistante

Le plan gratuit Render **ne garde pas les fichiers** entre les redéploiements.

**Solutions** :
- **Option 1** : Utilisez PostgreSQL Render (gratuit)
  - Créez une base PostgreSQL sur Render
  - Modifiez votre code pour utiliser PostgreSQL au lieu de SQLite
  
- **Option 2** : Utilisez un stockage externe
  - Amazon S3
  - Cloudinary
  - Render Disk (payant)

### 3. Variables d'environnement sensibles

Dans le dashboard Render → Environment :
- Ajoutez vos clés API
- Mots de passe admin
- Clés secrètes

### 4. Changer les mots de passe

Une fois déployé :
- Connectez-vous en tant qu'admin
- Changez TOUS les mots de passe par défaut

## 🔄 Auto-déploiement

À chaque `git push` sur GitHub, Render redéploie automatiquement !

```bash
git add .
git commit -m "Mise à jour"
git push origin main
```

## 📊 Plan Gratuit - Limitations

- ✅ 512 MB RAM
- ✅ SSL/HTTPS gratuit
- ⚠️ L'app s'éteint après 15 min d'inactivité
- ⚠️ Démarrage lent après inactivité (30-60 sec)
- ⚠️ 750 heures/mois max

## 🚀 Pour garder l'app toujours active

**Options** :
1. **Upgrade** vers un plan payant ($7/mois)
2. **Ping** votre app toutes les 10 minutes (service gratuit comme UptimeRobot)

## 🆘 Dépannage

### L'application ne démarre pas
- Vérifiez les **Logs** dans Render
- Assurez-vous que `gunicorn` est dans `requirements.txt`
- Vérifiez que la commande de démarrage est correcte

### Erreur de port
Render définit automatiquement `$PORT`. Utilisez :
```python
port = int(os.environ.get('PORT', 5000))
app.run(host='0.0.0.0', port=port)
```

### Base de données verrouillée
- Passez à PostgreSQL pour la production
- SQLite n'est pas idéal pour le web

## 📚 Ressources

- Documentation Render : https://render.com/docs/deploy-flask
- Dashboard Render : https://dashboard.render.com
- Support : https://render.com/docs

---

**Félicitations ! Votre plateforme Ttrust est maintenant en ligne ! 🎉**
