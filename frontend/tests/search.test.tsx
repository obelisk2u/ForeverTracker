import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as navigation from "next/navigation";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SearchBox } from "@/components/SearchBox";
import { SearchResults } from "@/components/SearchResults";
import type { SearchResponse } from "@/lib/types";

import search from "./fixtures/e2e/search.json";

const push = (navigation as unknown as { __push: ReturnType<typeof import("vitest").vi.fn> }).__push;

describe("SearchBox", () => {
  it("navigates to the search page with the query and namespace", async () => {
    push.mockClear();
    render(<SearchBox />);
    await userEvent.type(screen.getByLabelText("Character name"), "Asha Bright");
    await userEvent.selectOptions(screen.getByLabelText("Region and ruleset"), "eu-pve");
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(push).toHaveBeenCalledWith("/search?q=Asha+Bright&namespace=eu-pve");
  });

  it("asks for at least two characters", async () => {
    push.mockClear();
    render(<SearchBox />);
    await userEvent.type(screen.getByLabelText("Character name"), "a");
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(push).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("at least 2 characters");
  });
});

describe("SearchBox suggestions", () => {
  const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => ({ ok: true, json: async () => search }));
  beforeEach(() => {
    push.mockClear();
    fetchMock.mockClear();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("suggests matching characters as you type", async () => {
    render(<SearchBox compact />);
    await userEvent.type(screen.getByLabelText("Character name"), "brig");
    const list = await screen.findByRole("listbox", { name: "Matching characters" });
    const options = within(list).getAllByRole("option");
    expect(options.map((o) => o.textContent)).toEqual([
      expect.stringContaining("Thalen Brightvale"),
      expect.stringContaining("Asha Brightvale"),
      "See all results for “brig”",
    ]);
    expect(options[0]).toHaveTextContent("Hunter");
    expect(String(fetchMock.mock.calls.at(-1)?.[0])).toContain("/api/v1/search?q=brig&page_size=6");
  });

  it("opens a suggestion with the keyboard or a click", async () => {
    render(<SearchBox compact />);
    const box = screen.getByLabelText("Character name");
    await userEvent.type(box, "brig");
    await screen.findByRole("listbox");
    await userEvent.keyboard("{ArrowDown}{ArrowDown}{Enter}");
    expect(push).toHaveBeenCalledWith("/character/us-pve/6395cpuwfy");
    push.mockClear();
    await userEvent.type(box, "h");
    await userEvent.click(await screen.findByRole("option", { name: /Thalen Brightvale/ }));
    expect(push).toHaveBeenCalledWith("/character/us-pve/hdwfnhy7sy");
  });

  it("still searches everything with Enter, and Escape closes the list", async () => {
    render(<SearchBox />);
    await userEvent.type(screen.getByLabelText("Character name"), "brig");
    await screen.findByRole("listbox");
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("listbox")).toBeNull();
    await userEvent.keyboard("{Enter}");
    expect(push).toHaveBeenCalledWith("/search?q=brig");
  });

  it("waits for two characters before asking", async () => {
    render(<SearchBox compact />);
    await userEvent.type(screen.getByLabelText("Character name"), "b");
    await new Promise((r) => setTimeout(r, 250));
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("SearchResults", () => {
  it("lists characters that share a surname as separate people", () => {
    render(<SearchResults data={search as SearchResponse} />);
    const links = screen.getAllByRole("link");
    expect(links.map((l) => l.textContent)).toEqual(
      expect.arrayContaining([expect.stringContaining("Asha Brightvale"), expect.stringContaining("Thalen Brightvale")]),
    );
    expect(links[0].getAttribute("href")).toMatch(/^\/character\/us-pve\/[a-z0-9]+$/);
    expect(screen.queryByText(/share the name/)).toBeNull();
  });

  it("warns when several characters have the same full name", () => {
    const base = (search as SearchResponse).results[0];
    const data: SearchResponse = {
      ...(search as SearchResponse),
      total: 2,
      results: [base, { ...base, id: "zzzzzzzzzz", namespace: "eu-pve", namespace_display: "EU · Normal" }],
      duplicate_names: [base.full_name],
    };
    render(<SearchResults data={data} />);
    expect(screen.getByText(/Several characters share the name/)).toBeInTheDocument();
    expect(screen.getAllByText("same name as another result")).toHaveLength(2);
  });

  it("explains an empty result instead of showing a blank page", () => {
    render(<SearchResults data={{ query: "Nobody", exact: false, total: 0, page: 1, page_size: 20, results: [], duplicate_names: [] }} />);
    expect(screen.getByText(/No characters match/)).toBeInTheDocument();
    expect(screen.getByText(/only knows characters that appeared in a run/)).toBeInTheDocument();
  });
});
