"use client";

import { useRef } from "react";

import { AUTHOR_URL, REPO_URL } from "@/lib/site";
import type { UploaderRelease } from "@/lib/types";

const PRIMARY = "px-4 py-2 rounded-lg bg-gold text-ink font-semibold hover:bg-gold-strong focus-ring";
const SECONDARY = "px-4 py-2 rounded-lg border border-line text-text hover:bg-surface-2 focus-ring";
const LINK = "self-start underline text-text";

function Dropdown({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <details className="text-sm">
      <summary className="cursor-pointer text-text focus-ring rounded">{title}</summary>
      <div className="mt-2 flex flex-col gap-2">{children}</div>
    </details>
  );
}

// Windows warns about a new download until enough people have run it, signed or not, so the button first
// explains the warning, and the download starts from inside that explanation.
export function DownloadButton({ release }: { release: UploaderRelease }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const download = useRef<HTMLAnchorElement>(null);
  const file = release.download_url.split("/").pop() || `ForeverTracker-Setup-${release.version}.exe`;

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
          {release.signed ? (
            <p>
              ForeverTracker is signed, but it&apos;s new, and Windows warns about new downloads until enough people have
              run them. If Windows says it protected your PC, click <strong className="text-text">More info</strong>: the
              publisher should read <strong className="text-text">Jordan Stout</strong>. Then click{" "}
              <strong className="text-text">Run anyway</strong>.
            </p>
          ) : (
            <p>
              ForeverTracker is new and hasn&apos;t had time to be reviewed by Windows yet, so you&apos;ll see a warning when
              you download and run it. If Windows says it protected your PC, click{" "}
              <strong className="text-text">More info</strong>, then <strong className="text-text">Run anyway</strong>.
            </p>
          )}
          <Dropdown title="Check the file yourself">
            <p>
              Open PowerShell in your Downloads folder and run the command below. The hash it prints should match this
              one exactly.
            </p>
            <pre className="card p-3 text-xs text-text overflow-x-auto">{`Get-FileHash .\\${file}`}</pre>
            <code className="block break-all text-xs text-text">{release.sha256.toUpperCase()}</code>
          </Dropdown>
          <Dropdown title="See the code">
            <p>
              ForeverTracker is open source. Everything the app does, including exactly what it uploads, is in the public
              code, and this installer is built from it by GitHub Actions.
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
          <div className="mt-2 flex flex-wrap gap-3">
            <a ref={download} href={release.download_url} className={PRIMARY}>
              Download {file}
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
