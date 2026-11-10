import type { Metadata } from "next";

import { CharacterDirectory } from "@/components/CharacterDirectory";
import { EmptyState, Notice } from "@/components/States";
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
      <div>
        <h1 className="font-display text-3xl">Characters</h1>
        <p className="text-muted mt-2">Everyone seen in a recorded dungeon run, most-seen first.</p>
      </div>
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
