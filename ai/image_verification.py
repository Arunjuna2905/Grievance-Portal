from pathlib import Path

def verify_image(path):
    return bool(path and Path(path).suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp'})
