import type { Metadata } from "next";
import Link from "next/link";

import { Badge } from "@/components/Badges";
import { DownloadButton } from "@/components/DownloadButton";
import { PageHeader } from "@/components/States";
import { buttonVariants } from "@/components/ui/button";
import { api } from "@/lib/api";
import { CURSEFORGE_URL } from "@/lib/site";
import type { UploaderRelease } from "@/lib/types";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "Get the addon" };
export const dynamic = "force-dynamic";

const COMMANDS = [
  ["/ft", "your dungeon records (or click the minimap button)"],
  ["/ft end", "stop recording the dungeon run you are in"],
  ["/ft minimap", "show or hide the minimap button"],
  ["/ft status", "what is being recorded"],
  ["/ft probe", "test which APIs work"],
  ["/ft probe persist", "check that saved data survives a restart"],
  ["/ft collectors", "list and toggle collectors"],
  ["/ft purge confirm", "delete all stored data"],
];

export default async function DownloadPage() {
  // The same release installed apps update to; absent until one is published.
  const release: UploaderRelease | null = await api.uploaderRelease().catch(() => null);
  return (
    <div className="flex flex-col gap-10">
      <PageHeader
        title="Get the ForeverTracker addon"
        description="The addon runs entirely inside the game and never connects to the internet, so a small, nonintrusive companion app sends its records to ForeverTracker."
      />

      <div className="grid items-start gap-4 md:grid-cols-2">
        <section aria-labelledby="addon-only" className="flex h-full flex-col gap-3 rounded-xl border bg-card p-6">
          <h2 id="addon-only" className="text-lg font-semibold tracking-tight">
            Just the addon
          </h2>
          <p className="text-muted-foreground">
            Records your dungeon runs in game; type <code className="font-mono text-sm text-foreground">/ft</code> to see them. On
            its own it doesn&apos;t upload anything to this site.
          </p>
          <div className="mt-auto flex flex-wrap items-center gap-x-3 gap-y-1 pt-2">
            <a href={CURSEFORGE_URL} target="_blank" rel="noreferrer" className={cn(buttonVariants({ variant: "outline", size: "lg" }), "px-4")}>
              Get the addon on CurseForge ↗
            </a>
            <span className="text-sm text-faint">Opens curseforge.com</span>
          </div>
        </section>
        {release && (
          <section
            aria-labelledby="addon-and-app"
            className="relative flex h-full flex-col gap-3 rounded-xl border border-primary/30 bg-card p-6 shadow-[0_24px_64px_-40px_var(--primary)]"
          >
            <div className="flex items-start justify-between gap-3">
              <h2 id="addon-and-app" className="text-lg font-semibold tracking-tight">
                Addon + companion app <span className="text-base font-normal text-muted-foreground">(Windows)</span>
              </h2>
              <Badge tone="gold">Recommended</Badge>
            </div>
            <p className="text-muted-foreground">
              Puts your runs on ForeverTracker. Installs the addon if you don&apos;t have it, plus a small app that uploads what
              it records.
            </p>
            <div className="mt-auto flex flex-col gap-3 pt-2">
              <DownloadButton release={release} />
              <p className="text-sm text-faint">
                The app keeps itself up to date; the addon updates through CurseForge. See the{" "}
                <Link href="/code-signing" className="text-muted-foreground underline decoration-faint underline-offset-4 hover:text-foreground">
                  code signing policy
                </Link>
                .
              </p>
            </div>
          </section>
        )}
      </div>

      <div className="grid gap-10 md:grid-cols-2">
        <section aria-labelledby="commands" className="flex flex-col gap-3">
          <h2 id="commands" className="text-sm font-semibold">
            Commands
          </h2>
          <ul className="divide-y rounded-xl border bg-card text-sm">
            {COMMANDS.map(([cmd, text]) => (
              <li key={cmd} className="flex items-baseline gap-4 px-4 py-2.5">
                <code className="w-36 shrink-0 font-mono text-[13px] text-primary">{cmd}</code>
                <span className="text-muted-foreground">{text}</span>
              </li>
            ))}
          </ul>
        </section>
        <section id="uploader" aria-labelledby="companion" className="flex flex-col gap-3">
          <h2 id="companion" className="text-sm font-semibold">
            Companion app
          </h2>
          <p className="leading-relaxed text-muted-foreground">
            Addons cannot connect to the internet, so this small program is what gets your runs onto ForeverTracker. It
            watches the addon&apos;s SavedVariables file and uploads new records after you log out. It only reads files, never
            changes anything in your WoW folder, keeps a local copy of every version it sees, can be paused at any time, and
            shows exactly what it will send before sending it.
          </p>
        </section>
      </div>
    </div>
  );
}
