const API_URL =
  process.env.NEXT_PUBLIC_API_URL ??
  "http://localhost:8000";

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
      `${API_URL}/v2/auth/claim`,
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
   * Rotate the session. No body — the cookie carries the token, and script on
   * this page cannot read it, which is the point.
   */
  async refresh(): Promise<Session> {
    const response = await fetch(
      `${API_URL}/v2/auth/refresh`,
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
