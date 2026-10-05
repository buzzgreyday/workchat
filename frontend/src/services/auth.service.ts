import { apiUrl } from "@/lib/api";
import type { Challenge } from "@/lib/pow";

export interface Session {
  access_token: string;
  token_type: string;
  expires_in: number;
  refresh_expires_in: number;
}

export class AuthError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "AuthError";
    this.status = status;
  }
}

async function detail(
  response: Response,
): Promise<string> {
  try {
    const body = await response.json();

    return (
      body?.detail ??
      `Server returned ${response.status}`
    );
  } catch {
    return `Server returned ${response.status}`;
  }
}

class AuthService {
  /**
   * Trade a claim link for a session.
   *
   * `credentials: "include"` is load-bearing on both calls: the refresh token
   * comes back as an httpOnly cookie and is never in the body, so without it the
   * browser drops the only durable half of the session on the floor.
   */
  async claim(
    claimToken: string,
  ): Promise<Session> {
    const response = await fetch(
      `${apiUrl()}/v2/auth/claim`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        credentials: "include",
        body: JSON.stringify({
          claim_token: claimToken,
        }),
      },
    );

    if (!response.ok) {
      throw new AuthError(
        await detail(response),
        response.status,
      );
    }

    return response.json();
  }

  /**
   * A proof-of-work to solve before asking for a guest trial — and whether
   * one is offered at all: the backend answers 404 while trials are off, and
   * 429 to a browser that has had one recently. Stores nothing and sets
   * nothing, so asking is free.
   *
   * `credentials: "include"` so the trial cookie goes with it: it is what
   * says this browser has had its trial, and without it every visit would be
   * offered a new one.
   */
  async trialChallenge(): Promise<Challenge> {
    const response = await fetch(
      `${apiUrl()}/v2/auth/trial/challenge`,
      { credentials: "include" },
    );

    if (!response.ok) {
      throw new AuthError(
        await detail(response),
        response.status,
      );
    }

    return response.json();
  }

  /**
   * Trade a solved challenge for a guest session. Set up exactly as a claim's,
   * refresh cookie and all, so `credentials: "include"` matters here for the
   * same reason it does there.
   */
  async trial(
    solution: string,
  ): Promise<Session> {
    const response = await fetch(
      `${apiUrl()}/v2/auth/trial`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        credentials: "include",
        body: JSON.stringify({ solution }),
      },
    );

    if (!response.ok) {
      throw new AuthError(
        await detail(response),
        response.status,
      );
    }

    return response.json();
  }

  /**
   * Rotate the session. No body — the cookie carries the token, and script on
   * this page cannot read it, which is the point.
   */
  async refresh(): Promise<Session> {
    const response = await fetch(
      `${apiUrl()}/v2/auth/refresh`,
      {
        method: "POST",
        credentials: "include",
      },
    );

    if (!response.ok) {
      throw new AuthError(
        await detail(response),
        response.status,
      );
    }

    return response.json();
  }
}

export const authService = new AuthService();
