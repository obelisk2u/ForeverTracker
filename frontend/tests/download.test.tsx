import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

const { uploaderRelease } = vi.hoisted(() => ({ uploaderRelease: vi.fn() }));
vi.mock("@/lib/api", () => ({ api: { uploaderRelease } }));

import DownloadPage from "@/app/download/page";
import { REPO_URL } from "@/lib/site";

const url = "https://forevertracker.example/ForeverTracker-Setup-0.2.0.exe";
const release = { version: "0.2.0", download_url: url, sha256: "ab".repeat(32) };

describe("download page", () => {
  it("explains Windows' warning before an unsigned installer downloads", async () => {
    uploaderRelease.mockResolvedValue({ ...release, signed: false });
    render(await DownloadPage());
    const dialog = screen.getByRole("dialog", { hidden: true });
    expect(dialog).not.toHaveAttribute("open");
    // The page itself has no direct link to the file: the download starts from the explanation.
    expect(screen.queryByRole("link", { name: /Download/ })).toBeNull();
    // The button leads the page, ahead of the manual install steps.
    const button = screen.getByRole("button", { name: /Download for Windows · v0\.2\.0/ });
    const install = screen.getByRole("heading", { name: "Install" });
    expect(button.compareDocumentPosition(install) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    await userEvent.click(button);
    expect(dialog).toHaveAttribute("open");
    expect(within(dialog).getByText(/reviewed by Windows/)).toBeInTheDocument();
    expect(within(dialog).getByText("AB".repeat(32))).toBeInTheDocument();
    const download = within(dialog).getByRole("link", { name: "Download ForeverTracker-Setup-0.2.0.exe" });
    expect(download).toHaveAttribute("href", url);
    expect(download).toHaveFocus();
    expect(within(dialog).getByRole("link", { name: "See the code" })).toHaveAttribute("href", REPO_URL);

    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(dialog).not.toHaveAttribute("open");
  });

  it("links a signed installer directly", async () => {
    uploaderRelease.mockResolvedValue({ ...release, signed: true });
    render(await DownloadPage());
    expect(screen.getByRole("link", { name: /Download for Windows · v0\.2\.0/ })).toHaveAttribute("href", url);
    expect(screen.queryByRole("dialog", { hidden: true })).toBeNull();
  });

  it("shows only the from-source instructions until a release is published", async () => {
    uploaderRelease.mockRejectedValue(new Error("no desktop app release published"));
    render(await DownloadPage());
    expect(screen.queryByRole("button", { name: /Download for Windows/ })).toBeNull();
    expect(screen.queryByRole("link", { name: /Download for Windows/ })).toBeNull();
    expect(screen.getByText(/pip install \.\/uploader/)).toBeInTheDocument();
  });
});
