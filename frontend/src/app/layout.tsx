import type { Metadata } from "next";
import { connection } from "next/server";
import { Geist, Geist_Mono } from "next/font/google";

import { readOwner } from "@/lib/owner";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export async function generateMetadata(): Promise<Metadata> {
  // `await connection()` is not ceremony. A layout uses no request-time API of
  // its own, so without this Next may prerender the metadata and freeze the
  // title at build — which is exactly the baking this change exists to avoid.
  // Opting into dynamic rendering is what makes the environment readable here.
  await connection();

  const owner = readOwner();

  return {
    title: `Workchat with ${owner.name}`,
    description: `Ask ${owner.name}'s CV a question and get an answer from it, with the record it came from.`,
  };
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} antialiased`}
    >
      <body className="min-h-dvh flex flex-col">{children}</body>
    </html>
  );
}
