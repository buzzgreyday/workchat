/**
 * The longest question anyone may ask, in characters.
 *
 * Mirrors MAX_MESSAGE_CHARS in backend/app/common/config.py, which is the one
 * that is enforced — the server refuses anything longer. This copy is what
 * lets the composer stop at the limit and say so, rather than letting someone
 * type a paragraph only to be refused. Change both together.
 */
export const MAX_MESSAGE_CHARS = 150;
