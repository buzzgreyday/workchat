import Chat from "@/components/chat/Chat";

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

  return (
    <main className="chat-page-bg flex min-h-dvh items-center justify-center p-4">
      <Chat token={token} claim={claim} />
    </main>
  );
}
