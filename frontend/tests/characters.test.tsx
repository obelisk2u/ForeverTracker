import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CharacterDirectory } from "@/components/CharacterDirectory";
import type { CharacterListResponse, SearchResponse } from "@/lib/types";

import search from "./fixtures/e2e/search.json";

const [thalen, asha] = (search as SearchResponse).results;
const mah = { ...asha, id: "mahbeard01", name: "Mah", surname: "Beardlong", full_name: "Mah Beardlong", class_file: "WARRIOR" };

describe("characters list", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("adds the next page below with Show more, without repeating anyone", async () => {
    const page2: CharacterListResponse = { total: 3, page: 2, page_size: 2, results: [asha, mah] }; // asha moved down a page
    const fetchMock = vi.fn(async (_url: string) => ({ ok: true, json: async () => page2 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<CharacterDirectory initial={{ total: 3, page: 1, page_size: 2, results: [thalen, asha] }} />);
    expect(screen.getAllByRole("link")).toHaveLength(2);
    expect(screen.getByText("Showing 2 of 3")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Show more" }));
    expect(String(fetchMock.mock.calls[0][0])).toContain("/api/v1/characters?page=2&page_size=2");
    expect(screen.getAllByRole("link").map((l) => l.textContent)).toEqual([
      expect.stringContaining("Thalen Brightvale"),
      expect.stringContaining("Asha Brightvale"),
      expect.stringContaining("Mah Beardlong"),
    ]);
    expect(screen.getByText("Showing 3 of 3")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Show more" })).toBeNull();
  });

  it("says so when the next page fails to load, and keeps the button", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, statusText: "Bad Gateway" })));
    render(<CharacterDirectory initial={{ total: 3, page: 1, page_size: 2, results: [thalen, asha] }} />);
    await userEvent.click(screen.getByRole("button", { name: "Show more" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Couldn't load more characters");
    expect(screen.getByRole("button", { name: "Show more" })).toBeEnabled();
  });
});
