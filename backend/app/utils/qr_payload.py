"""
The text encoded in a PGDesk QR code.

    PGD1:R:<token>    a resident's identity card, scanned by a guard
    PGD1:G:<token>    a gate's own code, scanned by a resident

Why a prefix at all. A phone camera pointed at a gate will happily decode the
UPI sticker next to it, a delivery label, or a poster. Without a marker the
server would have to answer "not recognised" for all of that, which looks
identical to a genuine unknown resident and trains guards to ignore the message.
The prefix lets the client reject foreign codes before a request is ever made.

Why the version. The first field is `PGD1` rather than `PGD` so a future payload
change - a signed or rotating gate code, most likely - can be told apart from
this one by a scanner that has not been updated, instead of being mis-parsed.

Why the server still accepts a bare token. A hardware barcode gun is a keyboard:
it types whatever is in the symbol, prefix and all, into whichever field has
focus. Older PGs also have cards printed before this format existed, carrying
the bare token. Both must keep working, so parsing is forgiving on the way in
while generation is strict on the way out.
"""
from __future__ import annotations

PREFIX = "PGD1"
KIND_RESIDENT = "R"
KIND_GATE = "G"

#: Tokens are `secrets.token_urlsafe(24)`, which is 32 characters of the
#: URL-safe alphabet. The bound is generous rather than exact so a future token
#: length does not silently start failing to parse.
_MAX_TOKEN = 64


def encode(kind: str, token: str) -> str:
    """Build the string that goes into a QR symbol."""
    if kind not in (KIND_RESIDENT, KIND_GATE):
        raise ValueError(f"unknown QR kind {kind!r}")
    return f"{PREFIX}:{kind}:{token}"


def parse(raw: str | None) -> tuple[str | None, str]:
    """
    Pull the kind and token out of whatever was scanned or typed.

    Returns `(kind, token)`. `kind` is None when the input carried no prefix,
    which means the caller learns nothing about what the token is for and must
    look it up in the table it expects - the historical behaviour, preserved
    for bare cards and barcode guns.

    Never raises. A gate is the wrong place to surface a parse error, and every
    caller already has to handle "no such token" anyway.
    """
    if raw is None:
        return None, ""

    text = raw.strip()
    if not text:
        return None, ""

    parts = text.split(":")
    if len(parts) == 3 and parts[0].upper() == PREFIX:
        kind = parts[1].upper()
        if kind in (KIND_RESIDENT, KIND_GATE):
            return kind, parts[2].strip()[:_MAX_TOKEN]
        # A recognised prefix with an unrecognised kind is a newer card than
        # this build understands. Returning the raw text unchanged would send
        # "PGD1:X:abc" to a token lookup and answer "not recognised", which is
        # the honest outcome, so fall through rather than inventing a meaning.
        return None, ""

    return None, text[:_MAX_TOKEN]
