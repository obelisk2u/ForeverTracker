import type { Metadata } from "next";

import { CharacterDirectory } from "@/components/CharacterDirectory";
import { EmptyState, Notice, PageHeader } from "@/components/States";
import { api } from "@/lib/api";
import type { CharacterListResponse } from "@/lib/types";

export const metadata: Metadata = { title: "Characters" };
export const dynamic = "force-dynamic";

export default async function CharactersPage() {
  let data: CharacterListResponse | null = null;
  try {
    data = await api.characters();
  } catch {
    data = null;
  }
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Characters" description="Everyone seen in a recorded dungeon run, most-seen first." />
      {data === null ? (
        <Notice tone="warn">The character list is unavailable right now.</Notice>
      ) : data.total === 0 ? (
        <EmptyState title="No characters yet">Characters appear here once a dungeon run with them is uploaded.</EmptyState>
      ) : (
        <CharacterDirectory initial={data} />
      )}
    </div>
  );
}
