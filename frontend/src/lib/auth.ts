import { jwtDecode } from "jwt-decode";

interface JwtClaims {
  sub?: string;
}

export function getToken(): string {
  if (typeof window === "undefined") {
    return "";
  }

  return (
    new URLSearchParams(window.location.search).get("token") ?? ""
  );
}

export function getUserName(token: string): string {
  try {
    const claims = jwtDecode<JwtClaims>(token);

    return claims.sub ?? "You";
  } catch {
    return "You";
  }
}