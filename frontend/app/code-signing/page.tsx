import type { Metadata } from "next";
import Link from "next/link";

import { api } from "@/lib/api";
import { REPO_URL } from "@/lib/site";

export const metadata: Metadata = { title: "Code signing policy" };
export const dynamic = "force-dynamic";

export default async function CodeSigningPage() {
  const release = await api.uploaderRelease().catch(() => null);
  return (
    <article className="max-w-3xl flex flex-col gap-4 text-muted leading-relaxed">
      <h1 className="font-display text-3xl text-text">Code signing policy</h1>
      <p className="text-text">
        The Windows app and its installer are signed with{" "}
        <a href="https://azure.microsoft.com/products/artifact-signing" className="underline">
          Azure Artifact Signing
        </a>
        , Microsoft&apos;s code signing service. Windows shows the publisher as Jordan Stout.
      </p>
      {!release?.signed && (
        <p>Signed releases are on their way. Until then, the installer is unsigned and Windows warns about it.</p>
      )}

      <h2 className="font-display text-xl text-gold">What is signed</h2>
      <p>
        The Windows desktop app (ForeverTrackerUploader.exe) and its installer. Both are built by GitHub Actions from the
        public source code in the{" "}
        <a href={REPO_URL} className="underline">
          ForeverTracker repository
        </a>{" "}
        and signed in that same run. Only builds of the main branch are signed, and the signing certificate is held by
        Microsoft: it is never on anyone&apos;s computer. The addon is plain Lua source and is not signed.
      </p>

      <h2 className="font-display text-xl text-gold">Checking a download</h2>
      <p>
        Right-click the installer, choose Properties, and open the Digital Signatures tab: it should list Jordan Stout.
        The app only ever installs an update that carries the same signature, so a tampered download or server cannot
        replace it.
      </p>

      <h2 className="font-display text-xl text-gold">Who can sign</h2>
      <p>
        <a href="https://github.com/obelisk2u" className="underline">
          Jordan Stout
        </a>{" "}
        maintains ForeverTracker and is the only person who can change its code or start a signed release.
      </p>

      <h2 className="font-display text-xl text-gold">Privacy</h2>
      <p>
        The desktop app uploads the dungeon runs recorded by the addon to ForeverTracker, and checks once a day for a newer
        version. The <Link href="/privacy" className="underline">privacy notice</Link> lists exactly what it sends and how
        to turn it off, and the installer shows the same information before it installs anything.
      </p>
    </article>
  );
}
