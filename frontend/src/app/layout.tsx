import type { Metadata, Viewport } from "next";
import { connection } from "next/server";
import { Bebas_Neue } from "next/font/google";
import localFont from "next/font/local";

import { readOwner } from "@/lib/owner";
import "./globals.css";
// After globals.css, so this site's look overrides the plain defaults.
import "./theme.css";

// Variable fonts: one file per style covers every weight in the range, so
// `globals.css` can ask for any weight without a new file being added here.
const nunito = localFont({
  variable: "--font-nunito",
  src: [
    {
      path: "./fonts/nunito/Nunito-Variable.woff2",
      weight: "200 900",
      style: "normal",
    },
    {
      path: "./fonts/nunito/Nunito-VariableItalic.woff2",
      weight: "200 900",
      style: "italic",
    },
  ],
});

// A single weight, and capitals only — there is no bold to ask for, which is
// why `--text-title--font-weight` is 400. From Google rather than a file in
// `fonts/`: the Fontshare copy's licence forbids putting it in a public
// repository, and Google's is the same Dharma Type design under the OFL.
const bebas = Bebas_Neue({
  variable: "--font-bebas",
  weight: "400",
  subsets: ["latin"],
});

/**
 * Why a viewport export exists at all.
 *
 * Next's default meta tag is fine for width and scale, but says nothing about
 * the two things this page needs on a phone. `colorScheme` tells the browser to
 * paint its own surfaces — the canvas behind the document, the overscroll area,
 * the scrollbars — dark; without it they are white, which is what showed under
 * the chat. `interactiveWidget` asks for the on-screen keyboard to shorten the
 * layout viewport, so the `dvh` the layout is built on keeps meaning what the
 * layout assumes it means while someone is typing.
 *
 * Deliberately no `maximumScale` / `userScalable: false`. They are the usual
 * reflex against iOS zooming when a small field takes focus, but they take
 * pinch-zoom away from everyone; the composer asks for 16px on phones instead,
 * which fixes the same thing and costs nobody anything.
 */
export const viewport: Viewport = {
  colorScheme: "dark",

  // theme.css's --chat-bg converted to sRGB, so the browser chrome does not
  // sit a shade off the page it frames. Hand-converted and hardcoded because
  // a meta tag cannot read a custom property — if that `--chat-bg` moves,
  // this has to move with it.
  themeColor: "#1b3c53",

  interactiveWidget: "resizes-content",

  // Paint under the notch and the home indicator. Only safe because
  // `.chat-shell` pads the content back off them with `env(safe-area-inset-*)`
  // — and those insets only become non-zero once this is set. Neither half is
  // any use without the other.
  viewportFit: "cover",
};

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
      className={`${nunito.variable} ${bebas.variable} antialiased`}
    >
      <body className="h-full">{children}</body>
    </html>
  );
}
