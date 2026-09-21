import { jwtDecode } from "jwt-decode";

interface JwtClaims {
  sub?: string;
  // The grant. v2 separates the token's own id from the grant it belongs to;
  // on a v1 token `jti` is both.
  tid?: string;
  jti?: string;
}

/**
 * Which grant this token belongs to.
 *
 * Used to key anything cached per hirer, so a second link opened in the same
 * tab cannot be shown the first one's conversation. Empty when the token will
 * not decode, which callers should read as "cache nothing".
 */
export function getGrantId(token: string): string {
  try {
    const claims = jwtDecode<JwtClaims>(token);

    return claims.tid ?? claims.jti ?? "";
  } catch {
    return "";
  }
}

export function getUserName(token: string): string {
  try {
    const claims = jwtDecode<JwtClaims>(token);

    return claims.sub ?? "You";
  } catch {
    return "You";
  }
}