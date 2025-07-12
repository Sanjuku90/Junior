
class BiometricAuth {
  constructor() {
    this.isSupported = this.checkSupport();
    this.isEnabled = localStorage.getItem('biometric_enabled') === 'true';
  }

  checkSupport() {
    // Vérifier le support WebAuthn
    if (!window.PublicKeyCredential) {
      console.log('[Biometric] WebAuthn non supporté');
      return false;
    }

    // Vérifier si l'appareil a des capacités biométriques
    return PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable();
  }

  async isAvailable() {
    if (!this.isSupported) return false;
    
    try {
      return await PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable();
    } catch (error) {
      console.error('[Biometric] Erreur vérification disponibilité:', error);
      return false;
    }
  }

  async register(userId, userEmail) {
    if (!await this.isAvailable()) {
      throw new Error('Authentification biométrique non disponible');
    }

    try {
      const challengeResponse = await fetch('/api/biometric/challenge', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ userId, action: 'register' })
      });

      const { challenge, credentialId } = await challengeResponse.json();

      const publicKeyCredentialCreationOptions = {
        challenge: new Uint8Array(challenge),
        rp: {
          name: "Ttrust",
          id: location.hostname,
        },
        user: {
          id: new TextEncoder().encode(userId.toString()),
          name: userEmail,
          displayName: userEmail.split('@')[0],
        },
        pubKeyCredParams: [
          { alg: -7, type: "public-key" },
          { alg: -257, type: "public-key" }
        ],
        authenticatorSelection: {
          authenticatorAttachment: "platform",
          userVerification: "required",
          requireResidentKey: false
        },
        timeout: 60000,
        attestation: "direct"
      };

      const credential = await navigator.credentials.create({
        publicKey: publicKeyCredentialCreationOptions
      });

      // Envoyer la credential au serveur
      const registerResponse = await fetch('/api/biometric/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          userId,
          credentialId: Array.from(new Uint8Array(credential.rawId)),
          publicKey: Array.from(new Uint8Array(credential.response.publicKey)),
          attestationObject: Array.from(new Uint8Array(credential.response.attestationObject))
        })
      });

      if (registerResponse.ok) {
        this.isEnabled = true;
        localStorage.setItem('biometric_enabled', 'true');
        localStorage.setItem('biometric_credential_id', btoa(String.fromCharCode(...new Uint8Array(credential.rawId))));
        
        console.log('[Biometric] Authentification biométrique activée');
        return true;
      }

      throw new Error('Erreur lors de l\'enregistrement');
    } catch (error) {
      console.error('[Biometric] Erreur enregistrement:', error);
      throw error;
    }
  }

  async authenticate(userId) {
    if (!this.isEnabled || !await this.isAvailable()) {
      throw new Error('Authentification biométrique non disponible');
    }

    try {
      const challengeResponse = await fetch('/api/biometric/challenge', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ userId, action: 'authenticate' })
      });

      const { challenge } = await challengeResponse.json();
      const credentialId = localStorage.getItem('biometric_credential_id');

      if (!credentialId) {
        throw new Error('Aucune credential biométrique trouvée');
      }

      const publicKeyCredentialRequestOptions = {
        challenge: new Uint8Array(challenge),
        allowCredentials: [{
          id: Uint8Array.from(atob(credentialId), c => c.charCodeAt(0)),
          type: 'public-key',
          transports: ['internal']
        }],
        userVerification: 'required',
        timeout: 60000
      };

      const assertion = await navigator.credentials.get({
        publicKey: publicKeyCredentialRequestOptions
      });

      // Vérifier l'assertion avec le serveur
      const verifyResponse = await fetch('/api/biometric/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          userId,
          credentialId: Array.from(new Uint8Array(assertion.rawId)),
          authenticatorData: Array.from(new Uint8Array(assertion.response.authenticatorData)),
          signature: Array.from(new Uint8Array(assertion.response.signature)),
          clientDataJSON: Array.from(new Uint8Array(assertion.response.clientDataJSON))
        })
      });

      const result = await verifyResponse.json();
      return result.success;
    } catch (error) {
      console.error('[Biometric] Erreur authentification:', error);
      throw error;
    }
  }

  disable() {
    this.isEnabled = false;
    localStorage.removeItem('biometric_enabled');
    localStorage.removeItem('biometric_credential_id');
    console.log('[Biometric] Authentification biométrique désactivée');
  }

  // Interface utilisateur pour activation/désactivation
  showEnableDialog() {
    return new Promise((resolve) => {
      const dialog = document.createElement('div');
      dialog.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50';
      dialog.innerHTML = `
        <div class="bg-white rounded-lg p-6 max-w-sm mx-4">
          <div class="text-center">
            <div class="text-4xl mb-4">👆</div>
            <h3 class="text-lg font-semibold mb-2">Activer Touch ID / Face ID</h3>
            <p class="text-gray-600 mb-4">
              Utilisez votre empreinte digitale ou reconnaissance faciale pour sécuriser votre compte.
            </p>
            <div class="flex gap-3">
              <button id="enableBiometric" class="btn-primary flex-1">
                Activer
              </button>
              <button id="cancelBiometric" class="btn-secondary flex-1">
                Annuler
              </button>
            </div>
          </div>
        </div>
      `;

      document.body.appendChild(dialog);

      dialog.querySelector('#enableBiometric').onclick = () => {
        document.body.removeChild(dialog);
        resolve(true);
      };

      dialog.querySelector('#cancelBiometric').onclick = () => {
        document.body.removeChild(dialog);
        resolve(false);
      };
    });
  }
}

// Instance globale
window.biometricAuth = new BiometricAuth();
