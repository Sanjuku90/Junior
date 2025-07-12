
import os
from PIL import Image, ImageDraw, ImageFont
import math

def create_icon(size, filename):
    """Créer une icône avec logo crypto ultra-professionnel"""
    # Créer une image avec fond transparent
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Paramètres de design
    center_x, center_y = size // 2, size // 2
    margin = size // 12
    circle_radius = (size - 2 * margin) // 2
    
    # Fond avec dégradé sophistiqué (bleu corporate moderne)
    for y in range(size):
        progress = y / size
        # Dégradé du bleu foncé au bleu clair avec effet sophistiqué
        r = int(20 + (59 - 20) * progress)
        g = int(30 + (130 - 30) * progress)
        b = int(60 + (246 - 60) * progress)
        alpha = 255
        color = (r, g, b, alpha)
        draw.rectangle([(0, y), (size, y+1)], fill=color)
    
    # Cercle principal avec effet de profondeur
    shadow_offset = max(2, size // 64)
    
    # Ombre portée
    shadow_pos = (margin + shadow_offset, margin + shadow_offset, 
                  margin + circle_radius * 2 + shadow_offset, margin + circle_radius * 2 + shadow_offset)
    draw.ellipse(shadow_pos, fill=(0, 0, 0, 40))
    
    # Cercle principal avec bordure dorée
    circle_pos = (margin, margin, margin + circle_radius * 2, margin + circle_radius * 2)
    draw.ellipse(circle_pos, fill=(15, 23, 42, 255), outline=(255, 215, 0, 255), width=max(2, size//48))
    
    # Cercle intérieur avec dégradé subtil
    inner_margin = margin + max(4, size // 32)
    inner_circle_pos = (inner_margin, inner_margin, 
                       size - inner_margin, size - inner_margin)
    draw.ellipse(inner_circle_pos, fill=(25, 35, 55, 255))
    
    # Symbole crypto moderne et sophistiqué
    symbol_size = size // 2.5
    
    # Dessiner un logo "C" stylisé pour Crypto
    line_width = max(3, size // 24)
    
    # Calculer les positions pour le "C"
    c_radius = symbol_size // 2
    c_center_x, c_center_y = center_x, center_y
    
    # Créer le "C" avec des arcs élégants
    # Arc extérieur
    outer_bbox = (c_center_x - c_radius, c_center_y - c_radius,
                  c_center_x + c_radius, c_center_y + c_radius)
    
    # Arc intérieur
    inner_radius = c_radius - line_width
    inner_bbox = (c_center_x - inner_radius, c_center_y - inner_radius,
                  c_center_x + inner_radius, c_center_y + inner_radius)
    
    # Dessiner le "C" en or avec effet métallique
    # Partie principale du C
    angles = [180, 0]  # Ouverture à droite
    
    # Créer un masque pour le "C"
    mask = Image.new('L', (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    
    # Dessiner le cercle complet puis soustraire l'intérieur et l'ouverture
    mask_draw.ellipse(outer_bbox, fill=255)
    mask_draw.ellipse(inner_bbox, fill=0)
    
    # Créer l'ouverture du "C" (côté droit)
    opening_width = line_width * 1.5
    opening_bbox = (c_center_x, c_center_y - opening_width // 2,
                   c_center_x + c_radius + 5, c_center_y + opening_width // 2)
    mask_draw.rectangle(opening_bbox, fill=0)
    
    # Appliquer le dégradé doré
    for y in range(size):
        for x in range(size):
            if mask.getpixel((x, y)) > 0:
                # Effet métallique doré
                distance_from_top = y / size
                gold_intensity = 1.0 - distance_from_top * 0.3
                
                r = int(255 * gold_intensity)
                g = int(215 * gold_intensity)
                b = int(0 * gold_intensity)
                
                # Ajouter un effet de brillance
                distance_from_center = math.sqrt((x - center_x)**2 + (y - center_y)**2)
                if distance_from_center < c_radius * 0.3:
                    brightness = 1.2
                    r = min(255, int(r * brightness))
                    g = min(255, int(g * brightness))
                    b = min(255, int(b * brightness))
                
                draw.point((x, y), fill=(r, g, b, 255))
    
    # Ajouter des détails de finition
    # Points d'accent aux extrémités du "C"
    accent_size = max(2, size // 32)
    
    # Point haut
    top_y = center_y - c_radius + line_width // 2
    draw.ellipse((center_x - accent_size, top_y - accent_size,
                 center_x + accent_size, top_y + accent_size), 
                fill=(255, 255, 255, 200))
    
    # Point bas
    bottom_y = center_y + c_radius - line_width // 2
    draw.ellipse((center_x - accent_size, bottom_y - accent_size,
                 center_x + accent_size, bottom_y + accent_size), 
                fill=(255, 255, 255, 200))
    
    # Effet de brillance générale
    highlight_size = size // 5
    highlight_x = center_x - c_radius // 2
    highlight_y = center_y - c_radius // 2
    highlight_gradient = Image.new('RGBA', (highlight_size, highlight_size), (0, 0, 0, 0))
    highlight_draw = ImageDraw.Draw(highlight_gradient)
    
    for i in range(highlight_size):
        for j in range(highlight_size):
            distance = math.sqrt((i - highlight_size//2)**2 + (j - highlight_size//2)**2)
            if distance < highlight_size // 2:
                alpha = int(60 * (1 - distance / (highlight_size // 2)))
                highlight_draw.point((i, j), fill=(255, 255, 255, alpha))
    
    img.paste(highlight_gradient, (highlight_x, highlight_y), highlight_gradient)
    
    # Sauvegarder l'icône
    img.save(filename, 'PNG')
    print(f"✅ Icône créée: {filename} ({size}x{size})")

def create_favicon():
    """Créer le favicon.ico avec design professionnel"""
    sizes = [16, 32, 48]
    images = []
    
    for size in sizes:
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Fond dégradé corporate
        for y in range(size):
            progress = y / size
            r = int(15 + (59 - 15) * progress)
            g = int(23 + (130 - 23) * progress)
            b = int(42 + (246 - 42) * progress)
            draw.rectangle([(0, y), (size, y+1)], fill=(r, g, b, 255))
        
        # Symbole "C" simplifié pour favicon
        center = size // 2
        if size >= 32:
            # Version détaillée pour les grandes tailles
            radius = size // 3
            line_width = max(2, size // 16)
            
            # Cercle de fond
            draw.ellipse([center - radius, center - radius, center + radius, center + radius], 
                        fill=(255, 215, 0, 255))
            
            # Créer l'ouverture du "C"
            inner_radius = radius - line_width
            draw.ellipse([center - inner_radius, center - inner_radius, 
                         center + inner_radius, center + inner_radius], 
                        fill=(0, 0, 0, 0))
            
            # Ouverture droite
            draw.rectangle([center, center - line_width//2, size, center + line_width//2], 
                          fill=(0, 0, 0, 0))
        else:
            # Version ultra-simplifiée pour 16x16
            draw.ellipse([2, 2, size-2, size-2], fill=(255, 215, 0, 255))
            draw.ellipse([4, 4, size-4, size-4], fill=(0, 0, 0, 0))
            draw.rectangle([center, center-1, size, center+1], fill=(0, 0, 0, 0))
        
        images.append(img)
    
    # Sauvegarder le favicon
    images[0].save('static/favicon.ico', format='ICO', sizes=[(16, 16), (32, 32), (48, 48)])
    print("✅ Favicon créé: static/favicon.ico")

def main():
    """Créer toutes les icônes PWA avec design professionnel"""
    print("🎨 Création des icônes PWA professionnelles pour InvestCrypto Pro...")
    
    # Créer le dossier icons s'il n'existe pas
    os.makedirs('static/icons', exist_ok=True)
    
    # Tailles d'icônes PWA standard
    sizes = [16, 32, 72, 96, 128, 144, 152, 192, 384, 512]
    
    for size in sizes:
        filename = f'static/icons/icon-{size}x{size}.png'
        create_icon(size, filename)
    
    # Créer le favicon
    create_favicon()
    
    print("\n🎉 Icônes PWA professionnelles créées avec succès!")
    print("💼 Design corporate moderne avec logo 'C' doré sur fond dégradé bleu")
    print("📱 Optimisées pour tous les appareils et tailles d'écran!")

if __name__ == "__main__":
    main()
