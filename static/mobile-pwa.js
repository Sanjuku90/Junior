
class MobilePWA {
  constructor() {
    this.isStandalone = window.matchMedia('(display-mode: standalone)').matches;
    this.installPrompt = null;
    this.updateAvailable = false;
    this.init();
  }

  async init() {
    console.log('[PWA] Initialisation du mode mobile PWA...');
    
    // Initialiser les composants PWA
    await this.initServiceWorker();
    await this.initInstallPrompt();
    await this.initBiometricAuth();
    await this.initGeoSecurity();
    await this.initNotifications();
    
    // Optimisations mobiles
    this.setupMobileOptimizations();
    this.setupOfflineSync();
    this.setupBackgroundSync();
    
    console.log('[PWA] Initialisation terminée');
  }

  async initServiceWorker() {
    if ('serviceWorker' in navigator) {
      try {
        const registration = await navigator.serviceWorker.register('/static/sw.js');
        
        // Écouter les mises à jour
        registration.addEventListener('updatefound', () => {
          const newWorker = registration.installing;
          newWorker.addEventListener('statechange', () => {
            if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
              this.showUpdateNotification();
            }
          });
        });

        console.log('[PWA] Service Worker enregistré');
      } catch (error) {
        console.error('[PWA] Erreur Service Worker:', error);
      }
    }
  }

  async initInstallPrompt() {
    window.addEventListener('beforeinstallprompt', (e) => {
      e.preventDefault();
      this.installPrompt = e;
      this.showInstallBanner();
    });

    // Détecter si déjà installé
    if (this.isStandalone) {
      this.onAppInstalled();
    }
  }

  async initBiometricAuth() {
    if (window.biometricAuth) {
      const isAvailable = await window.biometricAuth.isAvailable();
      if (isAvailable && !window.biometricAuth.isEnabled) {
        this.suggestBiometricSetup();
      }
    }
  }

  async initGeoSecurity() {
    if (window.geoSecurity && window.geoSecurity.isEnabled) {
      const locationCheck = await window.geoSecurity.checkLocationSecurity();
      if (!locationCheck.safe) {
        await window.geoSecurity.handleSuspiciousLocation(locationCheck);
      }
    }
  }

  async initNotifications() {
    if (window.ttrustNotifications) {
      await window.ttrustNotifications.init();
      
      // Demander permission si pas encore accordée
      if (Notification.permission === 'default') {
        this.suggestNotificationSetup();
      }
    }
  }

  setupMobileOptimizations() {
    // Désactiver le zoom sur les inputs
    const viewport = document.querySelector('meta[name=viewport]');
    if (viewport) {
      viewport.content = 'width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no';
    }

    // Optimiser le scroll sur iOS
    document.body.style.webkitOverflowScrolling = 'touch';

    // Gérer l'orientation
    this.handleOrientationChange();
    window.addEventListener('orientationchange', () => {
      setTimeout(() => this.handleOrientationChange(), 100);
    });

    // Optimiser les performances
    this.setupPerformanceOptimizations();
  }

  setupOfflineSync() {
    // Stocker les données critiques en local
    window.addEventListener('online', () => {
      this.syncOfflineData();
      this.showConnectionStatus(true);
    });

    window.addEventListener('offline', () => {
      this.showConnectionStatus(false);
    });
  }

  setupBackgroundSync() {
    if ('serviceWorker' in navigator && 'sync' in window.ServiceWorkerRegistration.prototype) {
      navigator.serviceWorker.ready.then(registration => {
        // Programmer la synchronisation
        registration.sync.register('sync-investments');
        registration.sync.register('sync-security-logs');
      });
    }
  }

  showInstallBanner() {
    if (this.isStandalone) return;

    const banner = document.createElement('div');
    banner.id = 'installBanner';
    banner.className = 'fixed bottom-4 left-4 right-4 z-50 bg-blue-600 text-white p-4 rounded-lg shadow-lg';
    banner.innerHTML = `
      <div class="flex items-center justify-between">
        <div class="flex items-center">
          <i class="fas fa-mobile-alt mr-3"></i>
          <div>
            <div class="font-semibold">Installer Ttrust</div>
            <div class="text-sm opacity-90">Accès rapide depuis votre écran d'accueil</div>
          </div>
        </div>
        <div class="flex gap-2">
          <button id="installApp" class="bg-white text-blue-600 px-3 py-1 rounded font-medium">
            Installer
          </button>
          <button id="dismissInstall" class="text-white opacity-75 px-2">
            ✕
          </button>
        </div>
      </div>
    `;

    document.body.appendChild(banner);

    document.getElementById('installApp').onclick = () => this.installApp();
    document.getElementById('dismissInstall').onclick = () => banner.remove();

    // Auto-masquer après 10 secondes
    setTimeout(() => {
      if (banner.parentNode) banner.remove();
    }, 10000);
  }

  async installApp() {
    if (this.installPrompt) {
      this.installPrompt.prompt();
      const result = await this.installPrompt.userChoice;
      
      if (result.outcome === 'accepted') {
        console.log('[PWA] App installée');
        document.getElementById('installBanner')?.remove();
      }
      
      this.installPrompt = null;
    }
  }

  onAppInstalled() {
    // Optimisations post-installation
    document.body.classList.add('pwa-installed');
    
    // Cacher les éléments de navigation browser
    const elements = document.querySelectorAll('.browser-only');
    elements.forEach(el => el.style.display = 'none');

    // Notification bienvenue
    if (window.ttrustNotifications) {
      window.ttrustNotifications.showLocalNotification(
        '🎉 Ttrust installé!',
        { body: 'Bienvenue dans votre app mobile Ttrust' }
      );
    }
  }

  suggestBiometricSetup() {
    const dialog = document.createElement('div');
    dialog.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4';
    dialog.innerHTML = `
      <div class="bg-white rounded-xl p-6 max-w-sm w-full">
        <div class="text-center">
          <div class="text-4xl mb-4">🔒</div>
          <h3 class="text-lg font-bold mb-2">Sécuriser votre compte</h3>
          <p class="text-gray-600 mb-4">
            Activez Touch ID ou Face ID pour une connexion rapide et sécurisée.
          </p>
          <div class="flex gap-3">
            <button id="setupBiometric" class="flex-1 bg-blue-600 text-white py-2 px-4 rounded-lg font-medium">
              Activer
            </button>
            <button id="skipBiometric" class="flex-1 bg-gray-200 text-gray-700 py-2 px-4 rounded-lg font-medium">
              Plus tard
            </button>
          </div>
        </div>
      </div>
    `;

    document.body.appendChild(dialog);

    document.getElementById('setupBiometric').onclick = async () => {
      try {
        const userId = document.querySelector('[data-user-id]')?.dataset.userId;
        const userEmail = document.querySelector('[data-user-email]')?.dataset.userEmail;
        
        if (userId && userEmail) {
          await window.biometricAuth.register(userId, userEmail);
          this.showSuccess('Authentification biométrique activée!');
        }
      } catch (error) {
        this.showError('Erreur activation Touch ID/Face ID');
      }
      dialog.remove();
    };

    document.getElementById('skipBiometric').onclick = () => dialog.remove();
  }

  suggestNotificationSetup() {
    const dialog = document.createElement('div');
    dialog.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4';
    dialog.innerHTML = `
      <div class="bg-white rounded-xl p-6 max-w-sm w-full">
        <div class="text-center">
          <div class="text-4xl mb-4">🔔</div>
          <h3 class="text-lg font-bold mb-2">Notifications en temps réel</h3>
          <p class="text-gray-600 mb-4">
            Recevez des alertes pour vos profits, sécurité et support.
          </p>
          <div class="flex gap-3">
            <button id="enableNotifs" class="flex-1 bg-blue-600 text-white py-2 px-4 rounded-lg font-medium">
              Activer
            </button>
            <button id="skipNotifs" class="flex-1 bg-gray-200 text-gray-700 py-2 px-4 rounded-lg font-medium">
              Plus tard
            </button>
          </div>
        </div>
      </div>
    `;

    document.body.appendChild(dialog);

    document.getElementById('enableNotifs').onclick = async () => {
      const granted = await window.ttrustNotifications.requestPermission();
      if (granted) {
        this.showSuccess('Notifications activées!');
      }
      dialog.remove();
    };

    document.getElementById('skipNotifs').onclick = () => dialog.remove();
  }

  handleOrientationChange() {
    // Ajuster l'interface selon l'orientation
    const isLandscape = window.orientation === 90 || window.orientation === -90;
    document.body.classList.toggle('landscape', isLandscape);
    
    // Réajuster la hauteur viewport sur mobile
    const vh = window.innerHeight * 0.01;
    document.documentElement.style.setProperty('--vh', `${vh}px`);
  }

  setupPerformanceOptimizations() {
    // Lazy loading des images
    if ('IntersectionObserver' in window) {
      const imageObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            const img = entry.target;
            img.src = img.dataset.src;
            img.classList.remove('lazy');
            imageObserver.unobserve(img);
          }
        });
      });

      document.querySelectorAll('img[data-src]').forEach(img => {
        imageObserver.observe(img);
      });
    }

    // Optimiser les animations
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    if (prefersReducedMotion.matches) {
      document.body.classList.add('reduce-motion');
    }
  }

  async syncOfflineData() {
    try {
      // Synchroniser les données en attente
      const pendingData = this.getStoredPendingData();
      
      for (const data of pendingData) {
        await fetch(data.endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data.payload)
        });
      }

      this.clearStoredPendingData();
      console.log('[PWA] Synchronisation offline terminée');
    } catch (error) {
      console.error('[PWA] Erreur synchronisation:', error);
    }
  }

  getStoredPendingData() {
    const stored = localStorage.getItem('pending_sync_data');
    return stored ? JSON.parse(stored) : [];
  }

  clearStoredPendingData() {
    localStorage.removeItem('pending_sync_data');
  }

  showConnectionStatus(online) {
    const status = document.getElementById('connectionStatus');
    if (status) {
      status.className = online ? 'online' : 'offline';
      status.textContent = online ? 'En ligne' : 'Hors ligne';
    }

    // Notification toast
    const toast = document.createElement('div');
    toast.className = `fixed top-4 right-4 z-50 px-4 py-2 rounded-lg text-white ${online ? 'bg-green-500' : 'bg-red-500'}`;
    toast.textContent = online ? '🟢 Connexion rétablie' : '🔴 Mode hors ligne';
    
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
  }

  showUpdateNotification() {
    const banner = document.createElement('div');
    banner.className = 'fixed top-4 left-4 right-4 z-50 bg-green-600 text-white p-4 rounded-lg shadow-lg';
    banner.innerHTML = `
      <div class="flex items-center justify-between">
        <div>
          <div class="font-semibold">🎉 Mise à jour disponible</div>
          <div class="text-sm opacity-90">Nouvelles fonctionnalités et améliorations</div>
        </div>
        <button id="updateApp" class="bg-white text-green-600 px-3 py-1 rounded font-medium">
          Mettre à jour
        </button>
      </div>
    `;

    document.body.appendChild(banner);

    document.getElementById('updateApp').onclick = () => {
      window.location.reload();
    };

    setTimeout(() => banner.remove(), 8000);
  }

  showSuccess(message) {
    this.showToast(message, 'success');
  }

  showError(message) {
    this.showToast(message, 'error');
  }

  showToast(message, type = 'info') {
    const toast = document.createElement('div');
    const colors = {
      success: 'bg-green-500',
      error: 'bg-red-500',
      info: 'bg-blue-500'
    };

    toast.className = `fixed bottom-4 right-4 z-50 px-4 py-2 rounded-lg text-white ${colors[type]}`;
    toast.textContent = message;
    
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
  }
}

// Initialiser au chargement
document.addEventListener('DOMContentLoaded', () => {
  window.mobilePWA = new MobilePWA();
});

// Export pour utilisation globale
window.MobilePWA = MobilePWA;
