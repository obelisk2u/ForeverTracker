import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";

import { CharacterProfileView } from "@/components/CharacterProfileView";
import { EmptyState } from "@/components/States";
import { ApiError, api } from "@/lib/api";
import type { CharacterProfile } from "@/lib/types";

export const dynamic = "force-dynamic";

type Props = {
  params: Promise<{ namespace: string; id: string }>;
  searchParams: Promise<{ page?: string; dungeon?: string; role?: string; outcome?: string }>;
};

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { namespace, id } = await params;
  try {
    const p = await api.character(namespace, id);
    return { title: p.character.full_name, description: `Observed dungeon history of ${p.character.full_name} in World of Warcraft: Forever.` };
  } catch {
    return { title: "Character" };
  }
}

export default async function CharacterPage({ params, searchParams }: Props) {
  const { namespace, id } = await params;
  const sp = await searchParams;
  const page = Math.max(1, Number(sp.page ?? 1) || 1);
  let profile: CharacterProfile;
  try {
    profile = await api.character(namespace, id);
  } catch (e) {
    if (e instanceof ApiError && e.status === 410) {
      return (
        <EmptyState title="This profile is hidden">
          It was removed from public view at the request of its owner or by moderators.
        </EmptyState>
      );
    }
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }
  // Merged characters and namespace changes resolve to one stable URL.
  const requested = `/character/${namespace}/${id}`;
  if (profile.canonical_path !== requested) redirect(profile.canonical_path);

  const history = await api.runs(namespace, id, { page, dungeon: sp.dungeon, role: sp.role, outcome: sp.outcome });
  const filter = new URLSearchParams();
  if (sp.dungeon) filter.set("dungeon", sp.dungeon);
  if (sp.role) filter.set("role", sp.role);
  if (sp.outcome) filter.set("outcome", sp.outcome);
  const filterQuery = filter.toString() ? `&${filter.toString()}` : "";
  return (
    <CharacterProfileView profile={profile} history={history} page={page} filterQuery={filterQuery} />
  );
}
