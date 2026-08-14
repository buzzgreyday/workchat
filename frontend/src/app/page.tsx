import Chat from "@/components/chat/Chat";

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{ token?: string }>;
}) {
  const { token } = await searchParams;

  return (
    <main className="chat-page-bg flex min-h-dvh items-center justify-center p-4">
      <Chat token={token ?? ""} />
    </main>
  );
}