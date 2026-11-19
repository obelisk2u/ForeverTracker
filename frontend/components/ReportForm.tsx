"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
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
    <form onSubmit={submit} className="flex max-w-2xl flex-col gap-5">
      <label className="flex flex-col gap-2 text-sm">
        <span className="font-medium text-foreground">What is the problem?</span>
        <NativeSelect value={kind} onChange={(e) => setKind(e.target.value)} className="w-full [&_select]:h-10">
          {KINDS.map((k) => (
            <NativeSelectOption key={k.value} value={k.value}>
              {k.label}
            </NativeSelectOption>
          ))}
        </NativeSelect>
      </label>
      <div className="grid sm:grid-cols-2 gap-4">
        <label className="flex flex-col gap-2 text-sm">
          <span className="font-medium text-foreground">Character ID (from the profile URL)</span>
          <Input value={character} onChange={(e) => setCharacter(e.target.value)} maxLength={16} className="h-10 font-mono" />
        </label>
        <label className="flex flex-col gap-2 text-sm">
          <span className="font-medium text-foreground">Run ID (optional)</span>
          <Input value={run} onChange={(e) => setRun(e.target.value)} maxLength={16} className="h-10 font-mono" />
        </label>
      </div>
      <label className="flex flex-col gap-2 text-sm">
        <span className="font-medium text-foreground">Details</span>
        <textarea value={message} onChange={(e) => setMessage(e.target.value)} rows={5} maxLength={2000} className="rounded-lg border border-input bg-input/30 p-3 text-sm outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50" />
      </label>
      <p className="text-xs leading-relaxed text-faint">
        We do not ask for contact details. Suppression requests hide the profile and its name in other players&apos; run
        lists; we review requests to prevent abuse.
      </p>
      <Button type="submit" size="lg" className="self-start px-5 font-semibold">
        Send report
      </Button>
      {state && (
        <p role="status" className={state.ok ? "text-sm text-success" : "text-sm text-destructive"}>
          {state.text}
        </p>
      )}
    </form>
  );
}
