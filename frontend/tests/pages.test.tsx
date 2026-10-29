import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CharacterProfileView } from "@/components/CharacterProfileView";
import { RunDetailView } from "@/components/RunDetailView";
import { RunHistoryTable } from "@/components/RunHistoryTable";
import type { CharacterProfile, RunDetail, RunHistoryResponse } from "@/lib/types";

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
    expect(screen.getAllByText("Observer A").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Observer B").length).toBeGreaterThan(0);
    expect(screen.getByText(/not verified by Blizzard/)).toBeInTheDocument();
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
