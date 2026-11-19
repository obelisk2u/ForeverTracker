import type { Metadata } from "next";
import Link from "next/link";

import { Emblem } from "@/components/Emblem";
import { SearchBox } from "@/components/SearchBox";
import { SiteNav } from "@/components/SiteNav";
import { TooltipProvider } from "@/components/ui/tooltip";
import { REPO_URL } from "@/lib/site";

// Self-hosted fonts (SIL Open Font License): builds never depend on a third-party fetch.
import "@fontsource-variable/geist";
import "@fontsource-variable/geist-mono";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "ForeverTracker", template: "%s · ForeverTracker" },
  description:
    "Observed dungeon histories for World of Warcraft: Forever characters, assembled from ForeverTracker addon users. Not affiliated with Blizzard Entertainment.",
  icons: { icon: "/favicon.svg" },
};

const FOOTER = [
  { href: "/about", label: "Data collection" },
  { href: "/privacy", label: "Privacy" },
  { href: "/code-signing", label: "Code signing" },
  { href: "/report", label: "Report a problem" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="flex min-h-screen flex-col">
        <TooltipProvider delayDuration={150}>
          <header className="sticky top-0 z-30 border-b bg-background/85 backdrop-blur-md">
            <div className="mx-auto flex h-14 max-w-6xl items-center gap-6 px-4">
              <Link href="/" className="focus-ring flex shrink-0 items-center gap-2 rounded-md">
                <Emblem className="size-6" />
                <span className="hidden font-semibold tracking-tight sm:inline">ForeverTracker</span>
              </Link>
              <nav aria-label="Main" className="hidden items-center gap-0.5 md:flex">
                <SiteNav />
              </nav>
              <div className="ml-auto w-full max-w-xs min-w-0">
                <SearchBox compact />
              </div>
            </div>
            <nav aria-label="Main (mobile)" className="overflow-x-auto border-t md:hidden">
              <div className="flex gap-1 px-2 py-1.5">
                <SiteNav />
              </div>
            </nav>
          </header>
          <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 md:py-10">{children}</main>
          <footer className="border-t text-sm text-faint">
            <div className="mx-auto grid max-w-6xl gap-6 px-4 py-8 md:grid-cols-[1fr_auto] md:items-start">
              <div className="flex max-w-2xl gap-3">
                <Emblem className="mt-0.5 size-5 shrink-0 opacity-70" />
                <p>
                  ForeverTracker shows <em>observed</em> history: dungeon runs recorded by players who use the ForeverTracker
                  addon. Data is self-reported and not verified by Blizzard. World of Warcraft is a trademark of Blizzard
                  Entertainment, Inc.; ForeverTracker is not affiliated with or endorsed by Blizzard.
                </p>
              </div>
              <ul className="flex flex-wrap gap-x-5 gap-y-1">
                {FOOTER.map((f) => (
                  <li key={f.href}>
                    <Link href={f.href} className="focus-ring rounded-sm hover:text-foreground">
                      {f.label}
                    </Link>
                  </li>
                ))}
                <li>
                  <a href={REPO_URL} target="_blank" rel="noreferrer" className="focus-ring rounded-sm hover:text-foreground">
                    Source
                  </a>
                </li>
              </ul>
            </div>
          </footer>
        </TooltipProvider>
      </body>
    </html>
  );
}
