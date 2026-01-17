#!/usr/bin/env python3
"""
SOC Copilot Asset Generator
===========================

Generates application icons and other assets for desktop packaging.
Uses Pillow for reliable ICO generation.

Usage:
    python scripts/generate_assets.py

Output:
    assets/icon.ico - Windows multi-resolution icon
"""

import sys
from pathlib import Path


def create_shield_image(size: int):
    """Create a shield icon at the specified size using Pillow"""
    from PIL import Image, ImageDraw
    
    # Create RGBA image with dark background
    img = Image.new('RGBA', (size, size), (30, 30, 30, 255))
    draw = ImageDraw.Draw(img)
    
    # Calculate dimensions
    margin = max(2, size // 16)
    x, y = margin, margin
    s = size - (margin * 2)
    
    # Shield points
    shield_points = [
        (x + s/2, y),                    # Top center
        (x + s, y + s*0.3),              # Top right
        (x + s, y + s*0.6),              # Middle right
        (x + s/2, y + s),                # Bottom center (point)
        (x, y + s*0.6),                  # Middle left
        (x, y + s*0.3),                  # Top left
    ]
    
    # Draw shield fill (dark blue)
    draw.polygon(shield_points, fill=(30, 58, 95, 255))
    
    # Draw shield outline (cyan)
    pen_width = max(1, size // 32)
    draw.polygon(shield_points, outline=(0, 212, 255, 255))
    
    # Draw magnifying glass circle
    glass_x = x + s * 0.3
    glass_y = y + s * 0.25
    glass_size = s * 0.4
    
    # Circle outline
    bbox = [glass_x, glass_y, glass_x + glass_size, glass_y + glass_size]
    draw.ellipse(bbox, outline=(0, 212, 255, 255), width=pen_width)
    
    # Magnifying glass handle
    handle_start = (glass_x + glass_size * 0.8, glass_y + glass_size * 0.8)
    handle_end = (glass_x + glass_size * 1.3, glass_y + glass_size * 1.3)
    draw.line([handle_start, handle_end], fill=(0, 212, 255, 255), width=pen_width)
    
    return img


def generate_ico_file(output_path: Path):
    """Generate a Windows ICO file with multiple resolutions using Pillow"""
    from PIL import Image
    
    # Standard Windows icon sizes
    sizes = [16, 32, 48, 64, 128, 256]
    
    print(f"Generating icon with sizes: {sizes}")
    
    # Generate images at each size
    images = []
    for size in sizes:
        img = create_shield_image(size)
        images.append(img)
        print(f"  Generated {size}x{size}")
    
    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Save as ICO using Pillow (handles format correctly)
    # The first image is the "main" one, append others for multi-resolution
    main_image = images[0]
    other_images = images[1:]
    
    main_image.save(
        output_path,
        format='ICO',
        sizes=[(s, s) for s in sizes],
        append_images=other_images
    )
    
    file_size = output_path.stat().st_size
    print(f"\n[OK] Created {output_path.name} ({file_size:,} bytes)")
    return True


def main():
    print("SOC Copilot Asset Generator")
    print("=" * 40)
    
    project_root = Path(__file__).parent.parent
    assets_dir = project_root / "assets"
    
    # Ensure assets directory exists
    assets_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate icon
    icon_path = assets_dir / "icon.ico"
    
    try:
        success = generate_ico_file(icon_path)
        if success:
            print(f"\n[OK] Assets generated successfully")
            print(f"  Icon: {icon_path}")
            return 0
    except ImportError as e:
        print(f"Error: Pillow not available: {e}")
        print("Install with: pip install pillow")
        return 1
    except Exception as e:
        print(f"Error generating assets: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 1


if __name__ == "__main__":
    sys.exit(main())
