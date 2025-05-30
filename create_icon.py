#!/usr/bin/env python3
"""
Create a simple app icon for Whisper Transcription UI
Creates a microphone icon with a waveform background
"""

import os
from PIL import Image, ImageDraw, ImageFont
import subprocess

def create_icon_image(size=1024):
    """Create a simple icon with microphone and waveform"""
    # Create new image with Tokyo Night background color
    img = Image.new('RGBA', (size, size), (26, 27, 38, 255))  # #1a1b26
    draw = ImageDraw.Draw(img)
    
    # Tokyo Night blue color
    blue_color = (122, 162, 247, 255)  # #7aa2f7
    darker_blue = (86, 126, 211, 255)  # Slightly darker
    
    # Draw waveform background
    wave_height = size // 8
    wave_y = size // 2
    num_bars = 15
    bar_width = size // (num_bars * 2)
    
    for i in range(num_bars):
        x = i * (bar_width * 2) + bar_width // 2
        bar_height = wave_height * (0.3 + 0.7 * abs((i - num_bars // 2) / (num_bars // 2)))
        y1 = wave_y - bar_height // 2
        y2 = wave_y + bar_height // 2
        
        # Draw waveform bars with gradient effect
        color = blue_color if i % 2 == 0 else darker_blue
        draw.rectangle([x, y1, x + bar_width, y2], fill=color)
    
    # Draw microphone shape
    mic_width = size // 3
    mic_height = size // 2.5
    mic_x = (size - mic_width) // 2
    mic_y = size // 4
    
    # Microphone capsule (rounded rectangle)
    capsule_height = mic_height * 0.6
    draw.rounded_rectangle(
        [mic_x, mic_y, mic_x + mic_width, mic_y + capsule_height],
        radius=mic_width // 2,
        fill=blue_color,
        outline=(192, 202, 245, 255),  # #c0caf5
        width=size // 50
    )
    
    # Microphone stem
    stem_width = mic_width // 3
    stem_x = mic_x + (mic_width - stem_width) // 2
    stem_y = mic_y + capsule_height - size // 20
    stem_height = mic_height * 0.3
    
    draw.rectangle(
        [stem_x, stem_y, stem_x + stem_width, stem_y + stem_height],
        fill=blue_color
    )
    
    # Microphone base
    base_width = mic_width * 0.6
    base_x = mic_x + (mic_width - base_width) // 2
    base_y = stem_y + stem_height
    
    draw.ellipse(
        [base_x, base_y - size // 40, base_x + base_width, base_y + size // 20],
        fill=blue_color
    )
    
    # Add "W" text at bottom for Whisper
    try:
        font_size = size // 8
        # Try to use a system font, fallback to default if not available
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
        except:
            font = ImageFont.load_default()
        
        text = "W"
        # Get text bounding box for centering
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        text_x = (size - text_width) // 2
        text_y = size - size // 6 - text_height // 2
        
        draw.text((text_x, text_y), text, fill=(192, 202, 245, 255), font=font)
    except:
        # If font rendering fails, just skip the text
        pass
    
    return img

def create_icns_file():
    """Create the macOS .icns file"""
    # Create the icon at different sizes
    sizes = [16, 32, 64, 128, 256, 512, 1024]
    
    # Create temporary directory for icon files
    temp_dir = "/tmp/whisper_icon_temp"
    os.makedirs(temp_dir, exist_ok=True)
    
    # Create iconset directory
    iconset_dir = os.path.join(temp_dir, "app_icon.iconset")
    os.makedirs(iconset_dir, exist_ok=True)
    
    # Generate icons at different sizes
    for size in sizes:
        # Normal resolution
        img = create_icon_image(size)
        img.save(os.path.join(iconset_dir, f"icon_{size}x{size}.png"))
        
        # Retina resolution (except for 1024)
        if size < 1024:
            img_2x = create_icon_image(size * 2)
            img_2x_resized = img_2x.resize((size, size), Image.Resampling.LANCZOS)
            img_2x_resized.save(os.path.join(iconset_dir, f"icon_{size}x{size}@2x.png"))
    
    # Create the .icns file
    output_path = "resources/app_icon.icns"
    subprocess.run([
        "iconutil", "-c", "icns", iconset_dir, "-o", output_path
    ], check=True)
    
    # Clean up
    subprocess.run(["rm", "-rf", temp_dir])
    
    print(f"✅ Icon created successfully at: {output_path}")

if __name__ == "__main__":
    try:
        # First check if PIL is available
        create_icns_file()
    except ImportError:
        print("❌ PIL/Pillow not installed. Installing...")
        subprocess.run(["pip", "install", "Pillow"], check=True)
        print("✅ Pillow installed. Please run this script again.")
    except Exception as e:
        print(f"❌ Error creating icon: {e}")
        print("\nAs a fallback, you can:")
        print("1. Use any PNG image as your icon")
        print("2. Convert it to ICNS using: iconutil -c icns icon.iconset")
        print("3. Or use an online converter like cloudconvert.com")