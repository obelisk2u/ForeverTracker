import Link from "next/link";

import { ClassDot } from "@/components/Badges";
import { classColor } from "@/lib/game";
import { isHidden, type CharacterSummary, type HiddenCharacter } from "@/lib/types";

export function characterPath(c: CharacterSummary): string {
  return `/character/${c.namespace}/${c.id}`;
}

export function CharacterLink({ character, showDot = true }: { character: CharacterSummary | HiddenCharacter; showDot?: boolean }) {
  if (isHidden(character)) {
    return <span className="text-faint italic">Hidden character</span>;
  }
  return (
    <Link href={characterPath(character)} className="focus-ring inline-flex min-w-0 items-center gap-1.5 rounded-sm decoration-current/40 underline-offset-[3px] hover:underline">
      {showDot && <ClassDot classFile={character.class_file} />}
      <span className="truncate" style={{ color: classColor(character.class_file) }}>
        {character.full_name}
      </span>
    </Link>
  );
}
