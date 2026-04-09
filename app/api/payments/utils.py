import os
from typing import Optional

from cryptography.fernet import Fernet

# Initialize the encryptor with your secret key from .env
# KEEP THIS KEY SECRET. IF YOU LOSE IT, ALL STORED CARDS ARE LOST FOREVER.
encryption_key = os.environ.get("VCC_ENCRYPTION_KEY")
if encryption_key is None:
    raise RuntimeError("VCC_ENCRYPTION_KEY is not set")

fernet = Fernet(encryption_key.encode())

def encrypt_data(plain_text: Optional[str]) -> Optional[str]:
    if not plain_text:
        return None
    return fernet.encrypt(plain_text.encode()).decode()

def decrypt_data(cipher_text: Optional[str]) -> Optional[str]:
    if not cipher_text:
        return None
    return fernet.decrypt(cipher_text.encode()).decode()
