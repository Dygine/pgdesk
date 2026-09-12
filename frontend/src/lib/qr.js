/**
 * The text carried inside a PGuru QR code.
 *
 *     PGD1:R:<token>   a resident's card, scanned by a guard
 *     PGD1:G:<token>   a gate's own code, scanned by a resident
 *     PGD1:L:<token>   a one-time sign-in code, scanned on the login screen
 *
 * A line-for-line mirror of `app/utils/qr_payload.py`. Both sides have to agree
 * or a card printed by one is unreadable by the other, so if you change the
 * format here, change it there in the same commit.
 *
 * The prefix earns its place on the client more than on the server. A camera
 * pointed at a gate sees the UPI sticker beside it, a courier label, a poster.
 * Without a marker every one of those would become a request that comes back
 * "not recognised" - indistinguishable from a genuinely unknown resident, and a
 * good way to teach a guard to ignore the message. With it, foreign codes are
 * dropped before the scanner even stops.
 */
export const PREFIX = 'PGD1'
export const KIND_RESIDENT = 'R'
export const KIND_GATE = 'G'
/** A 30-minute, single-use sign-in key shown by the PG to a new resident. */
export const KIND_LOGIN = 'L'
const KINDS = [KIND_RESIDENT, KIND_GATE, KIND_LOGIN]

/** Build the string that goes into a symbol. */
export function encode(kind, token) {
  if (!KINDS.includes(kind)) {
    throw new Error(`unknown QR kind ${kind}`)
  }
  return `${PREFIX}:${kind}:${token}`
}

/**
 * Pull the kind and token out of whatever was scanned or typed.
 *
 * `kind` is null when there was no prefix, which means the input tells us
 * nothing about what it is for - a card printed before this format existed, or
 * a token typed by hand. Those still work; the server looks them up in the
 * table it expects. Never throws: a gate is the wrong place for a parse error.
 */
export function parse(raw) {
  if (!raw) return { kind: null, token: '' }
  const text = String(raw).trim()
  if (!text) return { kind: null, token: '' }

  const parts = text.split(':')
  if (parts.length === 3 && parts[0].toUpperCase() === PREFIX) {
    const kind = parts[1].toUpperCase()
    if (KINDS.includes(kind)) {
      return { kind, token: parts[2].trim() }
    }
    // A newer card than this build understands. Reporting it as unreadable is
    // honest; guessing at the meaning of an unknown kind is not.
    return { kind: null, token: '' }
  }
  return { kind: null, token: text }
}

/**
 * Is this one of ours at all?
 *
 * Used by the camera loop to decide whether to keep looking. Deliberately
 * permissive about bare tokens: a legacy card has no marker, and refusing to
 * accept it at the camera while the server still would is the kind of
 * inconsistency that makes a feature feel broken.
 */
export function looksLikeOurs(raw) {
  const { kind, token } = parse(raw)
  return kind !== null || token.length >= 8
}
