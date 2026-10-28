"use client";

import { useState } from "react";

import { apiBase } from "@/lib/api";

const KINDS = [
  { value: "suppression_request", label: "Hide a profile (opt out)" },
  { value: "incorrect_identity", label: "Wrong identity (two characters merged, or the wrong character)" },
  { value: "incorrect_statistics", label: "Incorrect statistics or run data" },
  { value: "other", label: "Something else" },
];

export function ReportForm({ characterId = "", runId = "" }: { characterId?: string; runId?: string }) {
  const [kind, setKind] = useState(characterId ? "suppression_request" : "incorrect_statistics");
  const [character, setCharacter] = useState(characterId);
  const [run, setRun] = useState(runId);
  const [message, setMessage] = useState("");
  const [state, setState] = useState<{ ok: boolean; text: string } | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (message.trim().length < 10) {
      setState({ ok: false, text: "Please describe the problem in at least 10 characters." });
      return;
    }
    const res = await fetch(`${apiBase()}/api/v1/reports`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind, message: message.trim(), character_id: character || null, run_id: run || null }),
    }).catch(() => null);
    if (res?.ok) {
      const body = await res.json();
      setState({ ok: true, text: `Thank you. Your report ${body.report_id} will be reviewed.` });
      setMessage("");
    } else {
      setState({ ok: false, text: res?.status === 404 ? "That character or run ID was not found." : "The report could not be sent." });
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4 max-w-2xl">
      <label className="flex flex-col gap-1 text-sm">
        <span className="text-muted">What is the problem?</span>
        <select value={kind} onChange={(e) => setKind(e.target.value)} className="h-10 rounded-md bg-surface-2 border border-line px-2">
          {KINDS.map((k) => (
            <option key={k.value} value={k.value}>
              {k.label}
            </option>
          ))}
        </select>
      </label>
      <div className="grid sm:grid-cols-2 gap-4">
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-muted">Character ID (from the profile URL)</span>
          <input value={character} onChange={(e) => setCharacter(e.target.value)} maxLength={16} className="h-10 rounded-md bg-surface-2 border border-line px-3" />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-muted">Run ID (optional)</span>
          <input value={run} onChange={(e) => setRun(e.target.value)} maxLength={16} className="h-10 rounded-md bg-surface-2 border border-line px-3" />
        </label>
      </div>
      <label className="flex flex-col gap-1 text-sm">
        <span className="text-muted">Details</span>
        <textarea value={message} onChange={(e) => setMessage(e.target.value)} rows={5} maxLength={2000} className="rounded-md bg-surface-2 border border-line p-3" />
      </label>
      <p className="text-xs text-faint">
        We do not ask for contact details. Suppression requests hide the profile and its name in other players&apos; run
        lists; we review requests to prevent abuse.
      </p>
      <button type="submit" className="self-start h-10 px-5 rounded-lg bg-gold text-ink font-semibold hover:bg-gold-strong focus-ring">
        Send report
      </button>
      {state && (
        <p role="status" className={state.ok ? "text-good text-sm" : "text-bad text-sm"}>
          {state.text}
        </p>
      )}
    </form>
  );
}
