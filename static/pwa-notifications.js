
class TtrustNotifications {
  constructor() {
    this.swRegistration = null;
    this.isSupported = 'serviceWorker' in navigator && 'PushManager' in window;
    this.permission = Notification.permission;
  }

  async init() {
    if (!this.isSupported) {
      console.warn('[Notifications] Push notifications non supportées');
      return false;
    }

    try {
      this.swRegistration = await navigator.serviceWorker.ready;
      console.log('[Notifications] Service Worker prêt');
      return true;
    } catch (error) {
      console.error('[Notifications] Erreur initialisation:', error);
      return false;
    }
  }

  async requestPermission() {
    if (!this.isSupported) return false;

    try {
      const permission = await Notification.requestPermission();
      this.permission = permission;
      
      if (permission === 'granted') {
        await this.subscribeUser();
        return true;
      }
      
      return false;
    } catch (error) {
      console.error('[Notifications] Erreur permission:', error);
      return false;
    }
  }

  async subscribeUser() {
    try {
      const subscription = await this.swRegistration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: this.urlBase64ToUint8Array(
          'BEl62iUYgUivxIkv69yViEuiBIa40HI80NqILj7Ox04bsZJfJdS9DY0wQ8-dafBIDKhZOhPGKgRNFDd_4SBQj5w'
        )
      });

      // Envoyer l'abonnement au serveur
      await fetch('/api/push-subscribe', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(subscription)
      });

      console.log('[Notifications] Utilisateur abonné aux notifications push');
      return true;
    } catch (error) {
      console.error('[Notifications] Erreur abonnement:', error);
      return false;
    }
  }

  urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding)
      .replace(/\-/g, '+')
      .replace(/_/g, '/');

    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);

    for (let i = 0; i < rawData.length; ++i) {
      outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
  }

  // Notifications locales pour interactions importantes
  showLocalNotification(title, options = {}) {
    if (this.permission !== 'granted') return;

    const defaultOptions = {
      body: 'Nouvelle notification Ttrust',
      icon: '/static/icons/icon-192x192.png',
      badge: '/static/icons/icon-72x72.png',
      vibrate: [200, 100, 200],
      tag: 'ttrust-local',
      requireInteraction: false
    };

    new Notification(title, { ...defaultOptions, ...options });
  }

  // Notification pour nouveaux profits
  notifyProfit(amount, plan) {
    this.showLocalNotification(`💰 Nouveau profit reçu!`, {
      body: `+${amount} USDT de votre plan ${plan}`,
      tag: 'profit',
      vibrate: [100, 50, 100],
      actions: [
        { action: 'view', title: 'Voir dashboard' }
      ]
    });
  }

  // Notification de sécurité
  notifySecurity(message, critical = false) {
    this.showLocalNotification(`🔐 Alerte sécurité`, {
      body: message,
      tag: 'security',
      requireInteraction: critical,
      vibrate: critical ? [300, 100, 300, 100, 300] : [200, 100, 200],
      actions: [
        { action: 'view_security', title: 'Vérifier' },
        { action: 'lock_account', title: 'Verrouiller compte' }
      ]
    });
  }

  // Notification de support
  notifySupport(ticketId, response) {
    this.showLocalNotification(`💬 Réponse support`, {
      body: `Nouvelle réponse sur votre ticket #${ticketId}`,
      tag: 'support',
      actions: [
        { action: 'view_ticket', title: 'Voir ticket' }
      ]
    });
  }
}

// Instance globale
window.ttrustNotifications = new TtrustNotifications();
