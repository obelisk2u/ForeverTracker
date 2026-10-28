// API types generated from docs/openapi.json (npm run gen:api).
import type { components } from "./api-schema";

type S = components["schemas"];

export type CharacterSummary = S["CharacterSummary"];
export type HiddenCharacter = S["HiddenCharacter"];
export type SearchResponse = S["SearchResponse"];
export type CharacterProfile = S["CharacterProfile"];
export type RunHistoryResponse = S["RunHistoryResponse"];
export type RunRow = S["RunRow"];
export type PartyMember = S["PartyMemberOut"];
export type MetricOut = S["MetricOut"];
export type MetricCandidate = S["MetricCandidateOut"];
export type RunDetail = S["RunDetail"];
export type Participant = S["ParticipantOut"];
export type EncounterOut = S["EncounterOut"];
export type DeathOut = S["DeathOut"];
export type WipeOut = S["WipeOut"];
export type SourceOut = S["SourceOut"];
export type ActivityItem = S["ActivityItem"];
export type OverviewStats = S["OverviewStats"];
export type MetaOut = S["MetaOut"];
export type UploadResult = S["UploadResult"];
export type UploaderRelease = S["UploaderRelease"];
export type GearSnapshot = S["GearSnapshotOut"];
export type DungeonRef = S["DungeonRef"];

export interface StatValue {
  definition: string;
  value: number | null;
  sample_size: number;
  excluded: number;
  exclusion_reasons: Record<string, number>;
  note: string | null;
}

export function isHidden(c: CharacterSummary | HiddenCharacter): c is HiddenCharacter {
  return (c as HiddenCharacter).hidden === true;
}
