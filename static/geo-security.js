
class GeoSecurity {
  constructor() {
    this.isSupported = 'geolocation' in navigator;
    this.lastKnownLocation = this.getStoredLocation();
    this.securityRadius = 50000; // 50km par défaut
    this.isEnabled = localStorage.getItem('geo_security_enabled') === 'true';
  }

  getStoredLocation() {
    const stored = localStorage.getItem('last_known_location');
    return stored ? JSON.parse(stored) : null;
  }

  storeLocation(position) {
    const location = {
      latitude: position.coords.latitude,
      longitude: position.coords.longitude,
      timestamp: Date.now(),
      accuracy: position.coords.accuracy
    };
    
    localStorage.setItem('last_known_location', JSON.stringify(location));
    this.lastKnownLocation = location;
    
    return location;
  }

  async getCurrentPosition() {
    if (!this.isSupported) {
      throw new Error('Géolocalisation non supportée');
    }

    return new Promise((resolve, reject) => {
      const options = {
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 300000 // 5 minutes
      };

      navigator.geolocation.getCurrentPosition(
        position => resolve(position),
        error => reject(error),
        options
      );
    });
  }

  calculateDistance(lat1, lon1, lat2, lon2) {
    const R = 6371000; // Rayon de la Terre en mètres
    const dLat = this.toRadians(lat2 - lat1);
    const dLon = this.toRadians(lon2 - lon1);
    
    const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
              Math.cos(this.toRadians(lat1)) * Math.cos(this.toRadians(lat2)) * 
              Math.sin(dLon/2) * Math.sin(dLon/2);
    
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
    return R * c;
  }

  toRadians(degrees) {
    return degrees * (Math.PI/180);
  }

  async checkLocationSecurity() {
    if (!this.isEnabled) return { safe: true, reason: 'disabled' };

    try {
      const position = await this.getCurrentPosition();
      const currentLocation = this.storeLocation(position);

      // Envoyer la localisation au serveur pour logging de sécurité
      await this.logLocationAccess(currentLocation);

      if (!this.lastKnownLocation) {
        return { safe: true, reason: 'first_access', location: currentLocation };
      }

      const distance = this.calculateDistance(
        this.lastKnownLocation.latitude,
        this.lastKnownLocation.longitude,
        currentLocation.latitude,
        currentLocation.longitude
      );

      if (distance > this.securityRadius) {
        return { 
          safe: false, 
          reason: 'location_change', 
          distance: Math.round(distance / 1000),
          location: currentLocation 
        };
      }

      return { safe: true, reason: 'same_location', location: currentLocation };
    } catch (error) {
      console.error('[GeoSecurity] Erreur vérification localisation:', error);
      return { safe: true, reason: 'error', error: error.message };
    }
  }

  async logLocationAccess(location) {
    try {
      await fetch('/api/security/location', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          latitude: location.latitude,
          longitude: location.longitude,
          accuracy: location.accuracy,
          timestamp: location.timestamp,
          user_agent: navigator.userAgent
        })
      });
    } catch (error) {
      console.error('[GeoSecurity] Erreur log localisation:', error);
    }
  }

  async reverseGeocode(lat, lon) {
    try {
      // Utiliser un service de géocodage inverse gratuit
      const response = await fetch(`https://api.bigdatacloud.net/data/reverse-geocode-client?latitude=${lat}&longitude=${lon}&localityLanguage=fr`);
      const data = await response.json();
      
      return {
        city: data.city || data.locality || 'Ville inconnue',
        country: data.countryName || 'Pays inconnu',
        region: data.principalSubdivision || data.region || ''
      };
    } catch (error) {
      console.error('[GeoSecurity] Erreur géocodage inverse:', error);
      return { city: 'Inconnu', country: 'Inconnu', region: '' };
    }
  }

  async handleSuspiciousLocation(locationCheck) {
    const geoInfo = await this.reverseGeocode(
      locationCheck.location.latitude,
      locationCheck.location.longitude
    );

    // Notification de sécurité
    if (window.ttrustNotifications) {
      window.ttrustNotifications.notifySecurity(
        `Connexion depuis une nouvelle localisation: ${geoInfo.city}, ${geoInfo.country} (${locationCheck.distance}km de votre dernière connexion)`,
        true
      );
    }

    // Demander confirmation utilisateur
    return this.showLocationConfirmDialog(geoInfo, locationCheck.distance);
  }

  showLocationConfirmDialog(geoInfo, distance) {
    return new Promise((resolve) => {
      const dialog = document.createElement('div');
      dialog.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50';
      dialog.innerHTML = `
        <div class="bg-white rounded-lg p-6 max-w-sm mx-4">
          <div class="text-center">
            <div class="text-4xl mb-4">🌍</div>
            <h3 class="text-lg font-semibold mb-2 text-red-600">Nouvelle localisation détectée</h3>
            <p class="text-gray-600 mb-4">
              Connexion depuis:<br>
              <strong>${geoInfo.city}, ${geoInfo.country}</strong><br>
              <small class="text-gray-500">À ${distance}km de votre dernière connexion</small>
            </p>
            <div class="flex gap-3">
              <button id="confirmLocation" class="btn-primary flex-1">
                C'est moi
              </button>
              <button id="denyLocation" class="btn-danger flex-1">
                Pas moi
              </button>
            </div>
          </div>
        </div>
      `;

      document.body.appendChild(dialog);

      dialog.querySelector('#confirmLocation').onclick = () => {
        document.body.removeChild(dialog);
        resolve(true);
      };

      dialog.querySelector('#denyLocation').onclick = () => {
        document.body.removeChild(dialog);
        resolve(false);
      };
    });
  }

  enable() {
    this.isEnabled = true;
    localStorage.setItem('geo_security_enabled', 'true');
    console.log('[GeoSecurity] Géolocalisation de sécurité activée');
  }

  disable() {
    this.isEnabled = false;
    localStorage.removeItem('geo_security_enabled');
    localStorage.removeItem('last_known_location');
    console.log('[GeoSecurity] Géolocalisation de sécurité désactivée');
  }
}

// Instance globale
window.geoSecurity = new GeoSecurity();
