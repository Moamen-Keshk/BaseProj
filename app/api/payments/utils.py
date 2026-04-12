import os
from functools import lru_cache
from typing import Optional

from cryptography.fernet import Fernet


@lru_cache(maxsize=1)
def get_fernet():
    encryption_key = os.environ.get("VCC_ENCRYPTION_KEY")
    if encryption_key is None:
        raise RuntimeError("VCC_ENCRYPTION_KEY is not set")
    return Fernet(encryption_key.encode())


def encrypt_data(plain_text: Optional[str]) -> Optional[str]:
    if not plain_text:
        return None
    return get_fernet().encrypt(plain_text.encode()).decode()


def decrypt_data(cipher_text: Optional[str]) -> Optional[str]:
    if not cipher_text:
        return None
    return get_fernet().decrypt(cipher_text.encode()).decode()
