"use client";

import { ChevronRight, Download, TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";

import { buttonVariants } from "@/components/ui/button";
import { AUTHOR_URL, REPO_URL } from "@/lib/site";
import type { UploaderRelease } from "@/lib/types";
import { cn } from "@/lib/utils";

const LINK = "self-start text-foreground underline decoration-faint underline-offset-4 hover:decoration-foreground";

function Dropdown({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <details className="group text-sm">
      <summary className="focus-ring flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-muted-foreground hover:text-foreground [&::-webkit-details-marker]:hidden">
        <ChevronRight aria-hidden="true" className="size-4 text-faint transition-transform group-open:rotate-90" />
        {title}
      </summary>
      <div className="flex flex-col gap-2 px-3 pb-3 pl-9 text-muted-foreground">{children}</div>
    </details>
  );
}

// The visitor's system when it is not Windows ("a Mac", "this device"), or null on Windows.
export function otherSystem(userAgent: string): string | null {
  if (/Windows/i.test(userAgent)) return null;
  return /Macintosh|Mac OS X/i.test(userAgent) ? "a Mac" : "this device";
}

// The button is a plain link to the installer: one click starts the download.
export function DownloadButton({ release }: { release: UploaderRelease }) {
  const file = release.download_url.split("/").pop() || `ForeverTracker-Setup-${release.version}.exe`;
  // The installer only runs on Windows; a Mac can't open it at all. Known only in the browser, after load.
  const [system, setSystem] = useState<string | null>(null);
  useEffect(() => setSystem(otherSystem(navigator.userAgent)), []);

  return (
    <>
      {system && (
        <p className="flex gap-2 rounded-lg border border-warning/25 bg-warning/5 px-3 py-2.5 text-sm text-warning">
          <TriangleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          The ForeverTracker companion app is for Windows, so it won&apos;t run on {system}. If you play World of Warcraft: Forever
          on a Windows PC, download it there.
        </p>
      )}
      <a href={release.download_url} className={cn(buttonVariants({ size: "lg" }), "self-start px-4 font-semibold")}>
        <Download aria-hidden="true" />
        Download for Windows · v{release.version}
      </a>
      <div className="divide-y rounded-lg border bg-background/40">
        <Dropdown title="Check the file yourself">
          <p>Open PowerShell in your Downloads folder and run the command below. The hash it prints should match this one exactly.</p>
          <pre className="overflow-x-auto rounded-md border bg-background p-3 font-mono text-xs text-foreground">{`Get-FileHash .\\${file}`}</pre>
          <code className="block font-mono text-xs break-all text-foreground">{release.sha256.toUpperCase()}</code>
        </Dropdown>
        <Dropdown title="See the code">
          <p>
            ForeverTracker is open source. Everything the app does, including exactly what it uploads, is in the public code,
            and this installer is built from it by GitHub Actions.
          </p>
          <a href={REPO_URL} target="_blank" rel="noreferrer" className={LINK}>
            {REPO_URL.replace("https://", "")}
          </a>
        </Dropdown>
        <Dropdown title="Meet the author">
          <p>ForeverTracker is made by Jordan Stout.</p>
          <a href={AUTHOR_URL} target="_blank" rel="noreferrer" className={LINK}>
            {AUTHOR_URL.replace("https://", "")}
          </a>
        </Dropdown>
      </div>
    </>
  );
}
