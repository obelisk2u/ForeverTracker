import type { Metadata } from "next";

import { DownloadButton } from "@/components/DownloadButton";
import { Notice } from "@/components/States";
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
          The addon records the dungeon runs you join. It runs entirely inside the game and never connects to the
          internet, so a small desktop app sends what it records to ForeverTracker.
        </p>
      </div>
      {release && (
        <div className="flex flex-col gap-2">
          <DownloadButton release={release} />
          <p className="text-sm text-muted">
            Installs the desktop app, plus the addon if you don&apos;t have it yet. The app keeps itself up to date; the
            addon updates through CurseForge.
          </p>
        </div>
      )}
      <Notice tone="warn">
        Pre-release: the addon has been tested against a simulated Forever client only. Some collectors (damage-meter
        totals, inspection, death tracking) still need confirming on the live client, and launch-day testers can help
        with <code>/ft probe</code>.
      </Notice>
      <section className="flex flex-col gap-3 text-muted">
        <h2 className="font-display text-xl text-gold">Install</h2>
        <ol className="list-decimal pl-5 space-y-1">
          <li>Download the ForeverTracker folder (release archive from the project repository).</li>
          <li>
            Copy it to <code className="text-text">World of Warcraft\_forever_\Interface\AddOns\ForeverTracker</code>.
          </li>
          <li>Start the game and check that ForeverTracker is enabled in the AddOns list.</li>
          <li>
            Type <code className="text-text">/ft status</code> in chat. <code className="text-text">/ft probe</code> reports which game
            features work on your client.
          </li>
        </ol>
      </section>
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
        {release && <p className="text-sm">The download above installs it. Or run it from source:</p>}
        <pre className="card p-3 text-xs text-text overflow-x-auto">{`pip install ./uploader
forevertracker-uploader setup --wow "C:\\Program Files (x86)\\World of Warcraft\\_forever_"
forevertracker-uploader disclose   # show what would be uploaded
forevertracker-uploader watch      # upload after each logout or /reload`}</pre>
      </section>
    </div>
  );
}
