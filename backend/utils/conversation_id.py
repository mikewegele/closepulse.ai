import hashlib


def normalize_conversation_id(raw: str, max_len: int = 128) -> str:
    if not raw: raise ValueError("missing conversation id")
    raw = raw.strip()
    if len(raw) <= max_len:
        return raw
    digest = hashlib.blake2s(raw.encode(), digest_size=10).hexdigest()  # 20 hex chars
    return raw[: max_len - 1 - len(digest)] + "_" + digest
