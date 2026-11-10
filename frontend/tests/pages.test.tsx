import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { CharacterProfileView } from "@/components/CharacterProfileView";
import { RunDetailView } from "@/components/RunDetailView";
import { RunHistoryTable } from "@/components/RunHistoryTable";
import { isHidden, type CharacterProfile, type RunDetail, type RunHistoryResponse } from "@/lib/types";

import history from "./fixtures/e2e/history.json";
import profile from "./fixtures/e2e/profile.json";
import run from "./fixtures/e2e/run.json";

// These fixtures are real API responses written by backend/tests/test_e2e_pipeline.py after the
// addon (in a Lua VM) recorded a run seen by two observers.
const p = profile as unknown as CharacterProfile;
const h = history as unknown as RunHistoryResponse;
const r = run as unknown as RunDetail;

describe("dungeon history", () => {
  it("renders the run with its metrics and a link to the run page", () => {
    render(<RunHistoryTable rows={h.items} characterId={p.character.id} />);
    const table = screen.getByTestId("history-table");
    const link = within(table).getByRole("link", { name: "Hall of Thanes" });
    expect(link).toHaveAttribute("href", `/runs/${h.items[0].run_id}`);
    expect(within(table).getByText("2 observers")).toBeInTheDocument();
    expect(within(table).getByText("Completed")).toBeInTheDocument();
    // The profile's own character is not repeated in the party column.
    const party = within(table).getByRole("list", { name: "Party" });
    expect(within(party).queryByText(p.character.full_name)).toBeNull();
    expect(within(party).getAllByRole("listitem")).toHaveLength(4);
  });

  it("has a card layout for small screens with the same data", () => {
    render(<RunHistoryTable rows={h.items} characterId={p.character.id} />);
    const table = screen.getByTestId("history-table");
    const cards = screen.getByTestId("history-cards");
    expect(table.className).toContain("hidden md:block");
    expect(cards.className).toContain("md:hidden");
    expect(within(cards).getByRole("link", { name: "Hall of Thanes" })).toBeInTheDocument();
  });
});

describe("run page", () => {
  it("shows every participant, reconciliation and preserved conflicts", () => {
    render(<RunDetailView run={r} />);
    expect(screen.getByRole("heading", { name: "Hall of Thanes" })).toBeInTheDocument();
    expect(screen.getByText("Reconciled from 2 observers")).toBeInTheDocument();
    for (const name of ["Autumn Redleaf", "Mah Beardlong", "Phineas Longhorn", "Asha Brightvale", "Thalen Brightvale"]) {
      expect(screen.getAllByText(name).length).toBeGreaterThan(0);
    }
    expect(screen.getAllByLabelText("observers disagree").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Killed")).toHaveLength(2);
    // No per-observer detail: who saw what, candidate values, or where the data came from.
    expect(screen.queryByText(/seen by/)).not.toBeInTheDocument();
    expect(screen.queryByText("Sources and candidate values")).not.toBeInTheDocument();
    expect(screen.queryByText("Where this data comes from")).not.toBeInTheDocument();
    expect(screen.queryByText("Observer A")).not.toBeInTheDocument();
  });
});

describe("run page fight picker", () => {
  it("shows one boss fight's numbers when it is picked", async () => {
    const mage = r.participants.find((x) => !isHidden(x.character) && x.character.full_name === "Autumn Redleaf")!;
    const id = (mage.character as { id: string }).id;
    const withFight: RunDetail = {
      ...r,
      encounters: r.encounters.map((e, i) =>
        i === 0 ? { ...e, combat_seconds: 40, metrics_status: "partial", metrics: { [id]: { damage_done: 8000, interrupts: 3 } } } : e,
      ),
    };
    render(<RunDetailView run={withFight} />);
    expect(screen.getByRole("button", { name: "Whole run" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("Presence")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Thane Ironvow" }));
    const row = screen.getAllByRole("row").find((tr) => within(tr).queryByText("Autumn Redleaf"))!;
    expect(within(row).getByText("8,000")).toBeInTheDocument();
    expect(within(row).getByText("200")).toBeInTheDocument(); // 8,000 damage over 40 s of combat
    expect(within(row).getByText("3")).toBeInTheDocument();
    expect(screen.queryByText("Presence")).toBeNull();
    expect(screen.getByText(/died during it/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "The Hollow King" }));
    expect(screen.getByText(/No damage-meter data/)).toBeInTheDocument();
  });
});

describe("run page gear", () => {
  it("shows what each person wore in the run", () => {
    const gear = {
      observed_at: "2026-10-14T17:58:00Z",
      source: "inspect",
      status: "observed",
      average_item_level: 21.5,
      level: 18,
      talents_status: null,
      items: [
        { slot: 1, slot_name: "Head", item_id: 1001, item_level: 22, enchant_id: null, gem_ids: [], quality: 3, link: "|cff0070dd|Hitem:1001::::::::20:::::|h[Thane's Helm]|h|r" },
        { slot: 16, slot_name: "Main Hand", item_id: 1016, item_level: 21, enchant_id: null, gem_ids: [], quality: 2, link: null },
      ],
    };
    const withGear: RunDetail = {
      ...r,
      participants: r.participants.map((x) => (!isHidden(x.character) && x.character.full_name === "Mah Beardlong" ? { ...x, gear } : { ...x, gear: null })),
    };
    render(<RunDetailView run={withGear} />);
    expect(screen.getByRole("heading", { name: "Gear" })).toBeInTheDocument();
    expect(screen.getByText("21.5")).toBeInTheDocument();
    expect(screen.getByText("Thane's Helm")).toHaveStyle({ color: "#0070dd" });
    expect(screen.getByText("Item 1016")).toBeInTheDocument(); // no link: the item ID stands in
    expect(screen.getAllByText("Gear not seen")).toHaveLength(4);
  });

  it("says so when nobody's gear was seen", () => {
    render(<RunDetailView run={{ ...r, participants: r.participants.map((x) => ({ ...x, gear: null })) }} />);
    expect(screen.getByText(/gear was seen during this run/)).toBeInTheDocument();
  });
});

describe("character profile", () => {
  it("shows identity, freshness, statistics and history", () => {
    render(<CharacterProfileView profile={p} history={h} page={1} />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Mah Beardlong");
    expect(screen.getByText("GUID-confirmed")).toBeInTheDocument();
    expect(screen.getByText("Last observed", { exact: false })).toBeInTheDocument();
    expect(screen.queryByText(/Observed history only/)).not.toBeInTheDocument();
    expect(screen.queryByText(/does not identify the account owner/)).not.toBeInTheDocument();
    expect(screen.queryByText("Latest known equipment")).not.toBeInTheDocument();
    expect(screen.getByText("1.00")).toBeInTheDocument(); // deaths per run
    expect(screen.getAllByRole("link", { name: "Hall of Thanes" }).length).toBeGreaterThan(0);
    expect(screen.getByText("10/14/26")).toBeInTheDocument(); // first observed
    expect(screen.queryByRole("link", { name: /Report incorrect data/ })).not.toBeInTheDocument();
  });
});
