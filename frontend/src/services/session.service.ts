import { AuthFetch } from "@/hooks/useSession";
import { Usage } from "@/types/chat";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ??
  "http://localhost:8000";

export interface SessionInfo {
  subject: string;
  version: number;
  usage: Usage;
  expires_at: string;
  session_id: string | null;
}

class SessionService {
  /**
   * The allowance, before anything is spent.
   *
   * Without this the header could only show a count once a question had already
   * been asked, so the one number a hirer wants up front — how many they get —
   * was the one thing they had to spend one to learn.
   */
  async get(
    authFetch: AuthFetch,
  ): Promise<SessionInfo> {
    const response = await authFetch(
      `${API_URL}/session`,
    );

    if (!response.ok) {
      throw new Error(
        `Server returned ${response.status}`,
      );
    }

    return response.json();
  }
}

export const sessionService =
  new SessionService();
