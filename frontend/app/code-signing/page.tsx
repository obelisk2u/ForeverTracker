import type { Metadata } from "next";
import Link from "next/link";

import { api } from "@/lib/api";
import { REPO_URL } from "@/lib/site";

export const metadata: Metadata = { title: "Code signing policy" };
export const dynamic = "force-dynamic";

// SignPath Foundation's roles. Every signing request is approved by hand.
const ROLES = [
  { role: "Authors", duty: "change the source code without further review" },
  { role: "Reviewers", duty: "review every change from outside contributors" },
  { role: "Approvers", duty: "approve each signing request" },
];

export default async function CodeSigningPage() {
  const release = await api.uploaderRelease().catch(() => null);
  return (
    <article className="max-w-3xl flex flex-col gap-4 text-muted leading-relaxed">
      <h1 className="font-display text-3xl text-text">Code signing policy</h1>
      <p className="text-text">
        Free code signing provided by{" "}
        <a href="https://about.signpath.io" className="underline">
          SignPath.io
        </a>
        , certificate by{" "}
        <a href="https://signpath.org" className="underline">
          SignPath Foundation
        </a>
      </p>
      {!release?.signed && (
        <p>
          ForeverTracker is joining SignPath Foundation&apos;s free signing program for open-source projects. Until signed
          releases are out, the installer is unsigned and Windows warns about it.
        </p>
      )}

      <h2 className="font-display text-xl text-gold">What is signed</h2>
      <p>
        The Windows desktop app (ForeverTrackerUploader.exe) and its installer. Both are built by GitHub Actions from the
        public source code in the{" "}
        <a href={REPO_URL} className="underline">
          ForeverTracker repository
        </a>
        , and a maintainer approves every signing request. The addon is plain Lua source and is not signed.
      </p>

      <h2 className="font-display text-xl text-gold">Team roles</h2>
      <ul className="list-disc pl-5 space-y-1">
        {ROLES.map(({ role, duty }) => (
          <li key={role}>
            <span className="text-text">{role}</span>, who {duty}:{" "}
            <a href="https://github.com/obelisk2u" className="underline">
              Jordan Stout
            </a>
          </li>
        ))}
      </ul>

      <h2 className="font-display text-xl text-gold">Privacy</h2>
      <p>
        The desktop app uploads the dungeon runs recorded by the addon to ForeverTracker, and checks once a day for a newer
        version. The <Link href="/privacy" className="underline">privacy notice</Link> lists exactly what it sends and how
        to turn it off, and the installer shows the same information before it installs anything.
      </p>
    </article>
  );
}
