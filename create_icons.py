
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
    
    # Dessiner un logo "T" stylisé pour Ttrust
    line_width = max(3, size // 24)
    
    # Calculer les positions pour le "T"
    t_width = symbol_size
    t_height = symbol_size
    t_center_x, t_center_y = center_x, center_y
    
    # Créer le "T" moderne et élégant
    # Créer un masque pour le "T"
    mask = Image.new('L', (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    
    # Barre horizontale du T (en haut)
    bar_top = t_center_y - t_height // 2
    bar_height = line_width
    horizontal_bar = (t_center_x - t_width // 2, bar_top,
                     t_center_x + t_width // 2, bar_top + bar_height)
    mask_draw.rectangle(horizontal_bar, fill=255)
    
    # Barre verticale du T (au centre)
    vertical_width = line_width
    vertical_bar = (t_center_x - vertical_width // 2, bar_top,
                   t_center_x + vertical_width // 2, t_center_y + t_height // 2)
    mask_draw.rectangle(vertical_bar, fill=255)
    
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
                if distance_from_center < t_width * 0.3:
                    brightness = 1.2
                    r = min(255, int(r * brightness))
                    g = min(255, int(g * brightness))
                    b = min(255, int(b * brightness))
                
                draw.point((x, y), fill=(r, g, b, 255))
    
    # Ajouter des détails de finition
    # Points d'accent aux extrémités du "T"
    accent_size = max(2, size // 32)
    
    # Points aux extrémités de la barre horizontale
    left_x = center_x - t_width // 2
    right_x = center_x + t_width // 2
    bar_y = center_y - t_height // 2 + line_width // 2
    
    draw.ellipse((left_x - accent_size, bar_y - accent_size,
                 left_x + accent_size, bar_y + accent_size), 
                fill=(255, 255, 255, 200))
    
    draw.ellipse((right_x - accent_size, bar_y - accent_size,
                 right_x + accent_size, bar_y + accent_size), 
                fill=(255, 255, 255, 200))
    
    # Point en bas de la barre verticale
    bottom_y = center_y + t_height // 2
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
    
    img.paste(highlight_gradient, (int(highlight_x), int(highlight_y)), highlight_gradient)
    
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
        
        # Symbole "T" simplifié pour favicon
        center = size // 2
        if size >= 32:
            # Version détaillée pour les grandes tailles
            t_size = size // 2
            line_width = max(2, size // 16)
            
            # Barre horizontale
            draw.rectangle([center - t_size//2, 2, center + t_size//2, 2 + line_width], 
                          fill=(255, 215, 0, 255))
            
            # Barre verticale
            draw.rectangle([center - line_width//2, 2, center + line_width//2, size - 2], 
                          fill=(255, 215, 0, 255))
        else:
            # Version ultra-simplifiée pour 16x16
            # Barre horizontale
            draw.rectangle([2, 2, size-2, 4], fill=(255, 215, 0, 255))
            # Barre verticale
            draw.rectangle([center-1, 2, center+1, size-2], fill=(255, 215, 0, 255))
        
        images.append(img)
    
    # Sauvegarder le favicon
    images[0].save('static/favicon.ico', format='ICO', sizes=[(16, 16), (32, 32), (48, 48)])
    print("✅ Favicon créé: static/favicon.ico")

def main():
    """Créer toutes les icônes PWA avec design professionnel"""
    print("🎨 Création des icônes PWA professionnelles pour Ttrust...")
    
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
    print("💼 Design corporate moderne avec logo 'T' doré sur fond dégradé bleu")
    print("📱 Optimisées pour tous les appareils et tailles d'écran!")

if __name__ == "__main__":
    main()
