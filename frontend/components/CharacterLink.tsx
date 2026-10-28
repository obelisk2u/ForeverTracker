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
    <Link href={characterPath(character)} className="inline-flex items-center gap-1.5 hover:underline focus-ring rounded-sm min-w-0">
      {showDot && <ClassDot classFile={character.class_file} />}
      <span className="truncate" style={{ color: classColor(character.class_file) }}>
        {character.full_name}
      </span>
    </Link>
  );
}
