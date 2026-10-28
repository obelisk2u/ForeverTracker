import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { RunDetailView } from "@/components/RunDetailView";
import { ApiError, api } from "@/lib/api";
import type { RunDetail } from "@/lib/types";

export const dynamic = "force-dynamic";

type Props = { params: Promise<{ id: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  try {
    const run = await api.run(id);
    return { title: `${run.dungeon.name} run` };
  } catch {
    return { title: "Dungeon run" };
  }
}

export default async function RunPage({ params }: Props) {
  const { id } = await params;
  let run: RunDetail;
  try {
    run = await api.run(id);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }
  return <RunDetailView run={run} />;
}
