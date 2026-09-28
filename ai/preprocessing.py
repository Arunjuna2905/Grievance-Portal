def clean_text(text):
    return ' '.join((text or '').lower().split())
