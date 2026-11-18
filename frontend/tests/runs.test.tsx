import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ActivityItem, RunListResponse } from "@/lib/types";

const runList = vi.fn();
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, api: { ...actual.api, runList: (...args: unknown[]) => runList(...args) } };
});

const { default: RunsPage } = await import("@/app/runs/page");
const { ApiError } = await import("@/lib/api");

function item(i: number, dungeon = { slug: "deadmines", name: "Deadmines", map_id: 36 }): ActivityItem {
  return {
    run_id: `run${i}`,
    dungeon,
    started_at: new Date(Date.UTC(2026, 10, 17 - i)).toISOString(),
    outcome: "completed",
    completion_confidence: "probable",
    participants: 5,
    observers: 1,
    is_synthetic: false,
  };
}

async function renderPage(searchParams: { page?: string; dungeon?: string } = {}) {
  render(await RunsPage({ searchParams: Promise.resolve(searchParams) }));
}

describe("run list page", () => {
  it("links to every run the home page counts, including the oldest", async () => {
    const data: RunListResponse = { total: 11, page: 1, page_size: 25, dungeon: null, results: Array.from({ length: 11 }, (_, i) => item(i)) };
    runList.mockResolvedValue(data);
    await renderPage();
    expect(runList).toHaveBeenLastCalledWith({ page: 1, pageSize: 25, dungeon: undefined });
    const links = within(screen.getByRole("list")).getAllByRole("link");
    expect(links).toHaveLength(11);
    expect(links[10]).toHaveAttribute("href", "/runs/run10");
    expect(screen.queryByRole("navigation", { name: "Pagination" })).toBeNull();
  });

  it("pages through a long list and keeps the dungeon filter", async () => {
    const dungeon = { slug: "deadmines", name: "Deadmines", map_id: 36 };
    runList.mockResolvedValue({ total: 30, page: 2, page_size: 25, dungeon, results: [item(25, dungeon)] });
    await renderPage({ page: "2", dungeon: "deadmines" });
    expect(runList).toHaveBeenLastCalledWith({ page: 2, pageSize: 25, dungeon: "deadmines" });
    expect(screen.getByRole("heading", { name: "Deadmines" })).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Pagination" });
    expect(within(nav).getByRole("link", { name: "Previous" })).toHaveAttribute("href", "/runs?page=1&dungeon=deadmines");
  });

  it("says so when a dungeon link is unknown", async () => {
    runList.mockImplementation(async () => {
      throw new ApiError(404, "dungeon not found");
    });
    await renderPage({ dungeon: "nowhere" });
    expect(screen.getByText("Unknown dungeon")).toBeInTheDocument();
  });
});
