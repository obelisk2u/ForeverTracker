import type { Metadata } from "next";

import { ReportForm } from "@/components/ReportForm";

export const metadata: Metadata = { title: "Report a problem" };

export default async function ReportPage({ searchParams }: { searchParams: Promise<{ character?: string; run?: string }> }) {
  const sp = await searchParams;
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-display text-3xl">Report a problem or opt out</h1>
        <p className="text-muted mt-2 max-w-2xl">
          Use this form to tell us that a profile mixes up two characters, that statistics look wrong, or that you want a
          profile hidden. Hidden profiles disappear from search and from other players&apos; run lists.
        </p>
      </div>
      <ReportForm characterId={sp.character ?? ""} runId={sp.run ?? ""} />
    </div>
  );
}
