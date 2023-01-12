import hashlib


def generate_finger_print(content):
    if not content:
        return None
    content = (content or '').strip().upper()
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
