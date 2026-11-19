import type { Metadata } from "next";

import { ReportForm } from "@/components/ReportForm";
import { PageHeader } from "@/components/States";

export const metadata: Metadata = { title: "Report a problem" };

export default async function ReportPage({ searchParams }: { searchParams: Promise<{ character?: string; run?: string }> }) {
  const sp = await searchParams;
  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        title="Report a problem or opt out"
        description={
          <>
            Use this form to tell us that a profile mixes up two characters, that statistics look wrong, or that you want a
            profile hidden. Hidden profiles disappear from search and from other players&apos; run lists.
          </>
        }
      />
      <ReportForm characterId={sp.character ?? ""} runId={sp.run ?? ""} />
    </div>
  );
}
