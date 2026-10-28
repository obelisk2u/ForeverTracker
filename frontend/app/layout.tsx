import type { Metadata } from "next";
import Link from "next/link";

import { SearchBox } from "@/components/SearchBox";
import { SyntheticBanner } from "@/components/SyntheticBanner";
import { Emblem } from "@/components/Emblem";

// Self-hosted fonts (SIL Open Font License): builds never depend on a third-party fetch.
import "@fontsource-variable/inter";
import "@fontsource/cinzel/600.css";
import "@fontsource/cinzel/700.css";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "ForeverTracker", template: "%s · ForeverTracker" },
  description:
    "Observed dungeon histories for World of Warcraft: Forever characters, assembled from ForeverTracker addon users. Not affiliated with Blizzard Entertainment.",
  icons: { icon: "/favicon.svg" },
};

const NAV = [
  { href: "/about", label: "How it works" },
  { href: "/download", label: "Get the addon" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen flex flex-col">
        <SyntheticBanner />
        <header className="border-b border-line/80 bg-ink/80 backdrop-blur sticky top-0 z-30">
          <div className="mx-auto max-w-6xl px-4 h-16 flex items-center gap-4">
            <Link href="/" className="flex items-center gap-2 shrink-0 focus-ring rounded-md">
              <Emblem className="h-7 w-7" />
              <span className="font-display text-lg tracking-wide text-gold hidden sm:inline">ForeverTracker</span>
            </Link>
            <div className="flex-1 min-w-0 max-w-md">
              <SearchBox compact />
            </div>
            <nav aria-label="Main" className="hidden md:flex items-center gap-1 text-sm">
              {NAV.map((n) => (
                <Link key={n.href} href={n.href} className="px-3 py-2 rounded-md text-muted hover:text-text hover:bg-surface-2 focus-ring">
                  {n.label}
                </Link>
              ))}
            </nav>
          </div>
          <nav aria-label="Main (mobile)" className="md:hidden border-t border-line/60 overflow-x-auto">
            <div className="flex gap-1 px-4 py-1 text-sm">
              {NAV.map((n) => (
                <Link key={n.href} href={n.href} className="px-3 py-1.5 rounded-md text-muted hover:text-text whitespace-nowrap focus-ring">
                  {n.label}
                </Link>
              ))}
            </div>
          </nav>
        </header>
        <main className="flex-1 mx-auto w-full max-w-6xl px-4 py-8">{children}</main>
        <footer className="border-t border-line/80 text-sm text-faint">
          <div className="mx-auto max-w-6xl px-4 py-8 grid gap-4 md:grid-cols-[1fr_auto]">
            <p className="max-w-2xl">
              ForeverTracker shows <em>observed</em> history: dungeon runs recorded by players who use the ForeverTracker
              addon. Data is self-reported and not verified by Blizzard. World of Warcraft is a trademark of Blizzard
              Entertainment, Inc.; ForeverTracker is not affiliated with or endorsed by Blizzard.
            </p>
            <div className="flex flex-wrap gap-x-4 gap-y-1">
              <Link href="/about" className="hover:text-text">Data collection</Link>
              <Link href="/privacy" className="hover:text-text">Privacy</Link>
              <Link href="/report" className="hover:text-text">Report a problem</Link>
            </div>
          </div>
        </footer>
      </body>
    </html>
  );
}
