
import os
from PIL import Image, ImageDraw, ImageFont
import math

def create_icon(size, filename):
    """Créer une icône avec logo crypto professionnel"""
    # Créer une image avec fond dégradé
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Fond dégradé bleu foncé vers bleu clair
    for y in range(size):
        alpha = int(255 * (1 - y / size * 0.3))
        color = (59, 130, 246, alpha)  # Bleu avec transparence
        draw.rectangle([(0, y), (size, y+1)], fill=color)
    
    # Créer un cercle de fond
    margin = size // 8
    circle_size = size - 2 * margin
    circle_pos = (margin, margin, margin + circle_size, margin + circle_size)
    
    # Cercle principal avec bordure
    draw.ellipse(circle_pos, fill=(15, 23, 42, 255), outline=(59, 130, 246, 255), width=max(1, size//64))
    
    # Symbole Bitcoin stylisé
    center_x, center_y = size // 2, size // 2
    symbol_size = size // 3
    
    # Dessiner le symbole ₿ stylisé
    font_size = symbol_size
    try:
        # Essayer d'utiliser une police système
        font = ImageFont.truetype("arial.ttf", font_size)
    except:
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", font_size)
        except:
            try:
                font = ImageFont.load_default()
            except:
                font = None
    
    # Dessiner le symbole Bitcoin ou ₿
    if font:
        symbol = "₿"
        bbox = draw.textbbox((0, 0), symbol, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        text_x = center_x - text_width // 2
        text_y = center_y - text_height // 2
        
        # Ombre du texte
        draw.text((text_x + 1, text_y + 1), symbol, font=font, fill=(0, 0, 0, 128))
        # Texte principal
        draw.text((text_x, text_y), symbol, font=font, fill=(255, 255, 255, 255))
    else:
        # Fallback: dessiner un B stylisé
        line_width = max(2, size // 32)
        
        # Barres verticales du B
        left_x = center_x - symbol_size // 3
        right_x = center_x + symbol_size // 4
        top_y = center_y - symbol_size // 2
        bottom_y = center_y + symbol_size // 2
        middle_y = center_y
        
        # Barre verticale gauche
        draw.rectangle([left_x - line_width//2, top_y, left_x + line_width//2, bottom_y], 
                      fill=(255, 255, 255, 255))
        
        # Barres horizontales
        draw.rectangle([left_x, top_y - line_width//2, right_x, top_y + line_width//2], 
                      fill=(255, 255, 255, 255))
        draw.rectangle([left_x, middle_y - line_width//2, right_x - line_width, middle_y + line_width//2], 
                      fill=(255, 255, 255, 255))
        draw.rectangle([left_x, bottom_y - line_width//2, right_x, bottom_y + line_width//2], 
                      fill=(255, 255, 255, 255))
        
        # Barres verticales droites (courbes du B)
        draw.rectangle([right_x - line_width, top_y, right_x, middle_y], 
                      fill=(255, 255, 255, 255))
        draw.rectangle([right_x - line_width, middle_y, right_x, bottom_y], 
                      fill=(255, 255, 255, 255))
    
    # Effets de brillance
    highlight_size = size // 6
    highlight_x = center_x - symbol_size // 3
    highlight_y = center_y - symbol_size // 3
    draw.ellipse([highlight_x, highlight_y, highlight_x + highlight_size, highlight_y + highlight_size], 
                fill=(255, 255, 255, 80))
    
    # Sauvegarder l'icône
    img.save(filename, 'PNG')
    print(f"✅ Icône créée: {filename} ({size}x{size})")

def create_favicon():
    """Créer le favicon.ico"""
    sizes = [16, 32, 48]
    images = []
    
    for size in sizes:
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Fond bleu simple
        draw.rectangle([0, 0, size, size], fill=(59, 130, 246, 255))
        
        # Symbole simplifié
        center = size // 2
        if size >= 32:
            # Pour les grandes tailles, dessiner un B simple
            line_width = max(1, size // 16)
            b_width = size // 2
            b_height = size // 2
            
            left = center - b_width // 2
            top = center - b_height // 2
            right = left + b_width
            bottom = top + b_height
            middle = (top + bottom) // 2
            
            # Dessiner le B
            draw.rectangle([left, top, left + line_width, bottom], fill=(255, 255, 255, 255))
            draw.rectangle([left, top, right - line_width, top + line_width], fill=(255, 255, 255, 255))
            draw.rectangle([left, middle - line_width//2, right - line_width, middle + line_width//2], fill=(255, 255, 255, 255))
            draw.rectangle([left, bottom - line_width, right, bottom], fill=(255, 255, 255, 255))
            draw.rectangle([right - line_width, top, right, middle], fill=(255, 255, 255, 255))
            draw.rectangle([right - line_width, middle, right, bottom], fill=(255, 255, 255, 255))
        else:
            # Pour les petites tailles, juste un point blanc
            draw.ellipse([center-2, center-2, center+2, center+2], fill=(255, 255, 255, 255))
        
        images.append(img)
    
    # Sauvegarder le favicon
    images[0].save('static/favicon.ico', format='ICO', sizes=[(16, 16), (32, 32), (48, 48)])
    print("✅ Favicon créé: static/favicon.ico")

def main():
    """Créer toutes les icônes PWA"""
    print("🎨 Création des icônes PWA pour InvestCrypto Pro...")
    
    # Créer le dossier icons s'il n'existe pas
    os.makedirs('static/icons', exist_ok=True)
    
    # Tailles d'icônes PWA standard
    sizes = [16, 32, 72, 96, 128, 144, 152, 192, 384, 512]
    
    for size in sizes:
        filename = f'static/icons/icon-{size}x{size}.png'
        create_icon(size, filename)
    
    # Créer le favicon
    create_favicon()
    
    print("\n🎉 Toutes les icônes PWA ont été créées avec succès!")
    print("📱 Votre application a maintenant un look professionnel sur tous les appareils!")

if __name__ == "__main__":
    main()
