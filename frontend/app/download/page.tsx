import type { Metadata } from "next";
import Link from "next/link";

import { DownloadButton } from "@/components/DownloadButton";
import { api } from "@/lib/api";
import type { UploaderRelease } from "@/lib/types";

export const metadata: Metadata = { title: "Get the addon" };
export const dynamic = "force-dynamic";

export default async function DownloadPage() {
  // The same release installed apps update to; absent until one is published.
  const release: UploaderRelease | null = await api.uploaderRelease().catch(() => null);
  return (
    <div className="max-w-3xl flex flex-col gap-8">
      <div>
        <h1 className="font-display text-3xl">Get the ForeverTracker addon</h1>
        <p className="text-muted mt-2">
          The addon runs entirely inside the game and never connects to the internet, so a small, nonintrusive desktop
          app sends its records to ForeverTracker.
        </p>
      </div>
      {release && (
        <div className="flex flex-col gap-2">
          <DownloadButton release={release} />
          <p className="text-sm text-muted">
            Installs the desktop app, plus the addon if you don&apos;t have it yet. The app keeps itself up to date; the
            addon updates through CurseForge. See the{" "}
            <Link href="/code-signing" className="underline">
              code signing policy
            </Link>
            .
          </p>
        </div>
      )}
      <section className="flex flex-col gap-3 text-muted">
        <h2 className="font-display text-xl text-gold">Commands</h2>
        <ul className="grid sm:grid-cols-2 gap-2 text-sm">
          {[
            ["/ft status", "what is being recorded"],
            ["/ft probe", "test which APIs work"],
            ["/ft probe persist", "check that saved data survives a restart"],
            ["/ft collectors", "list and toggle collectors"],
            ["/ft purge confirm", "delete all stored data"],
          ].map(([cmd, text]) => (
            <li key={cmd} className="card px-3 py-2">
              <code className="text-text">{cmd}</code> <span className="text-faint">· {text}</span>
            </li>
          ))}
        </ul>
      </section>
      <section id="uploader" className="flex flex-col gap-3 text-muted">
        <h2 className="font-display text-xl text-gold">Desktop uploader</h2>
        <p>
          Addons cannot connect to the internet, so this small program is what gets your runs onto ForeverTracker. It
          watches the addon&apos;s SavedVariables file and uploads new records after you log out. It only reads files,
          never changes anything in your WoW folder, keeps a local copy of every version it sees, can be paused at any
          time, and shows exactly what it will send before sending it.
        </p>
      </section>
    </div>
  );
}
