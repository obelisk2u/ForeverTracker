"use client";

import { useRef } from "react";

import { REPO_URL } from "@/lib/site";
import type { UploaderRelease } from "@/lib/types";

const PRIMARY = "px-4 py-2 rounded-lg bg-gold text-ink font-semibold hover:bg-gold-strong focus-ring";
const SECONDARY = "px-4 py-2 rounded-lg border border-line text-text hover:bg-surface-2 focus-ring";

// A signed installer downloads straight away. Until then Windows warns about it, so the button first
// explains the warning, and the download starts from inside that explanation.
export function DownloadButton({ release }: { release: UploaderRelease }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const download = useRef<HTMLAnchorElement>(null);
  const file = release.download_url.split("/").pop() || `ForeverTracker-Setup-${release.version}.exe`;

  if (release.signed) {
    return (
      <a href={release.download_url} className={`self-start ${PRIMARY}`}>
        Download for Windows · v{release.version}
      </a>
    );
  }

  return (
    <>
      <button
        type="button"
        onClick={() => {
          dialog.current?.showModal();
          download.current?.focus();
        }}
        className={`self-start ${PRIMARY}`}
      >
        Download for Windows · v{release.version}
      </button>
      <dialog
        ref={dialog}
        aria-labelledby="download-dialog-title"
        // A click on the dialog element itself (not its content) is a click on the backdrop.
        onClick={(e) => e.target === e.currentTarget && e.currentTarget.close()}
        className="card m-auto w-[calc(100%-2rem)] max-w-lg p-0 text-muted backdrop:bg-ink/80"
      >
        <div className="p-6 flex flex-col gap-3">
          <h2 id="download-dialog-title" className="font-display text-xl text-gold">
            Windows will probably warn you
          </h2>
          <p>
            ForeverTracker is new and hasn&apos;t had time to be reviewed by Windows yet, so you&apos;ll see a warning when
            you download and run it. If Windows says it protected your PC, click{" "}
            <strong className="text-text">More info</strong>, then <strong className="text-text">Run anyway</strong>.
          </p>
          <details className="text-sm">
            <summary className="cursor-pointer text-text focus-ring rounded">Check the file yourself</summary>
            <p className="mt-2">
              Open PowerShell in your Downloads folder and run the command below. The hash it prints should match this
              one exactly.
            </p>
            <pre className="card mt-2 p-3 text-xs text-text overflow-x-auto">{`Get-FileHash .\\${file}`}</pre>
            <code className="mt-2 block break-all text-xs text-text">{release.sha256.toUpperCase()}</code>
          </details>
          <div className="mt-2 flex flex-wrap gap-3">
            <a ref={download} href={release.download_url} className={PRIMARY}>
              Download {file}
            </a>
            <a href={REPO_URL} target="_blank" rel="noreferrer" className={SECONDARY}>
              See the code
            </a>
            <button type="button" onClick={() => dialog.current?.close()} className={SECONDARY}>
              Cancel
            </button>
          </div>
        </div>
      </dialog>
    </>
  );
}
