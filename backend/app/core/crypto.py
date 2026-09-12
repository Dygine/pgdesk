"""
Encryption for secrets that have to live in the database.

Used for one thing today: the SMTP password a master admin types into the
platform settings screen.

The original design read SMTP credentials from the environment and said so in a
comment - deployment secrets, not tenant preferences, not editable from a web
form. That reasoning is sound and the environment path is still honoured first.
But it makes the operator redeploy to change a mail password, and an operator
who cannot change a mail password without a developer will eventually not change
it at all. Storing it, encrypted, is the lesser of the two risks.

What this does and does not protect against:

  Protects   a database dump, a stolen backup, a read-only SQL injection, a
             support engineer with query access. In all of those the ciphertext
             is useless without the application secret, which lives in the
             environment and is not in the database.

  Does not   an attacker who already has the application's SECRET_KEY, or code
             execution on the server. They can decrypt it, because the running
             application must be able to. Nothing stored by an application that
             needs to use a secret can survive that, and pretending otherwise
             would be worse than saying it plainly.

The key is derived from SECRET_KEY rather than being a second secret to manage.
That couples them: rotating SECRET_KEY makes existing ciphertext undecryptable.
`decrypt` returns None in that case instead of raising, so the effect is "email
stops sending until the password is re-entered" rather than a crash on a screen
that has nothing to do with mail.
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

#: Distinguishes this key from any other future use of SECRET_KEY. Without a
#: label, two features deriving "a key" from the same secret would get the same
#: key, and a ciphertext from one would decrypt in the other.
_LABEL = b"pgguru.secretbox.v1"


def _key() -> bytes:
    digest = hashlib.sha256(_LABEL + settings.secret_key.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt(plaintext: str) -> str:
    """Ciphertext as a string, safe to put in a text column."""
    return Fernet(_key()).encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str | None) -> str | None:
    """
    Plaintext, or None if it cannot be read.

    None covers both "nothing stored" and "stored under a different SECRET_KEY".
    Callers treat the two the same way - the secret is unavailable - because
    there is no useful action that differs between them.
    """
    if not ciphertext:
        return None
    try:
        return Fernet(_key()).decrypt(ciphertext.encode()).decode()
    except (InvalidToken, ValueError):
        return None


def is_readable(ciphertext: str | None) -> bool:
    """Whether a stored secret can still be decrypted, without returning it."""
    return decrypt(ciphertext) is not None
