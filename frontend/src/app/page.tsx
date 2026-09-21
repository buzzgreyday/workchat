import Chat from "@/components/chat/Chat";
import { readOwner } from "@/lib/owner";

export default async function Home({
  searchParams,
}: {
  // ?token= is a v1 access token — the link is the credential, and those are
  // still in inboxes. ?claim= is a v2 claim token, exchanged once for a session.
  // Both are handed to the client component, which decides on the strength of
  // which one arrived; neither survives in the address bar past first load.
  searchParams: Promise<{
    token?: string;
    claim?: string;
  }>;
}) {
  const { token, claim } = await searchParams;

  // Awaiting searchParams above is what makes this render per request, which is
  // what makes the environment readable here at all — Next only guarantees a
  // runtime value during dynamic rendering. Handed down as a prop rather than
  // imported by the client component, so it stays out of the browser bundle.
  const owner = readOwner();

  return (
    // `h-full`, taking the height `html` was given rather than asserting one.
    // That height is the *visual* viewport where the browser reports it, which
    // is what keeps the composer above an iOS keyboard; three elements each
    // naming their own `dvh` is how they drift apart when it changes.
    <main className="bg-canvas chat-shell flex h-full min-h-0 items-center justify-center">
      <Chat
        token={token}
        claim={claim}
        owner={owner}
      />
    </main>
  );
}
