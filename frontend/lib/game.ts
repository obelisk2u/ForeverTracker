// Display data for classes, roles, outcomes and metrics.

export const CLASS_INFO: Record<string, { name: string; color: string }> = {
  WARRIOR: { name: "Warrior", color: "#C69B6D" },
  PALADIN: { name: "Paladin", color: "#F48CBA" },
  HUNTER: { name: "Hunter", color: "#AAD372" },
  ROGUE: { name: "Rogue", color: "#FFF468" },
  PRIEST: { name: "Priest", color: "#F5F5F5" },
  SHAMAN: { name: "Shaman", color: "#0070DD" },
  MAGE: { name: "Mage", color: "#3FC7EB" },
  WARLOCK: { name: "Warlock", color: "#8788EE" },
  DRUID: { name: "Druid", color: "#FF7C0A" },
};

export function className(file: string | null | undefined): string {
  if (!file) return "Unknown class";
  return CLASS_INFO[file]?.name ?? file.charAt(0) + file.slice(1).toLowerCase();
}

export function classColor(file: string | null | undefined): string {
  return (file && CLASS_INFO[file]?.color) || "#9ca3af";
}

const RACE_NAMES: Record<string, string> = {
  NightElf: "Night Elf",
  Scourge: "Undead",
  BloodElf: "Blood Elf",
  Skyborne: "Skyborne",
};

export function raceName(file: string | null | undefined): string {
  if (!file) return "Unknown race";
  return RACE_NAMES[file] ?? file.replace(/([a-z])([A-Z])/g, "$1 $2");
}

export const ROLE_LABEL: Record<string, string> = { TANK: "Tank", HEALER: "Healer", DAMAGER: "Damage", NONE: "No role" };

export function roleLabel(role: string | null | undefined): string {
  return (role && ROLE_LABEL[role]) || "Role unknown";
}

export const OUTCOME: Record<string, { label: string; tone: "good" | "bad" | "neutral" | "warn" }> = {
  completed: { label: "Completed", tone: "good" },
  abandoned: { label: "Abandoned", tone: "bad" },
  left: { label: "Left early", tone: "warn" },
  disconnected: { label: "Disconnected", tone: "warn" },
  in_progress: { label: "In progress", tone: "neutral" },
  unknown: { label: "Outcome unknown", tone: "neutral" },
};

export const METRIC_LABEL: Record<string, string> = {
  damage_done: "Damage",
  dps: "DPS",
  healing_done: "Healing",
  hps: "HPS",
  absorbs: "Absorbs",
  interrupts: "Interrupts",
  dispels: "Dispels",
  damage_taken: "Damage taken",
  avoidable_damage_taken: "Avoidable damage",
  deaths: "Deaths",
};

export const SOURCE_LABEL: Record<string, string> = {
  native_damage_meter: "Blizzard damage meter (via addon)",
  death_events: "Death state changes seen by addon users",
};

export const RESOLUTION_LABEL: Record<string, string> = {
  corroborated: "Corroborated by independent observers",
  single_source: "Reported by one observer",
  conflicted: "Observers disagree",
  conflict_resolved: "Sources disagreed; better-scoped source used",
};

export function namespaceLabel(slug: string): string {
  const [region, ruleset] = slug.split("-");
  const r = region === "unknown" ? "Unknown region" : region.toUpperCase();
  const rules: Record<string, string> = { pve: "Normal", pvp: "PvP", rp: "Roleplay", hardcore: "Hardcore", unknown: "Unknown ruleset" };
  return `${r} · ${rules[ruleset] ?? ruleset}`;
}
