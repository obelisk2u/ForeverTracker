import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

const { uploaderRelease } = vi.hoisted(() => ({ uploaderRelease: vi.fn() }));
vi.mock("@/lib/api", () => ({ api: { uploaderRelease } }));

import DownloadPage from "@/app/download/page";
import { AUTHOR_URL, REPO_URL } from "@/lib/site";

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
    const button = screen.getByRole("button", { name: /Download for Windows · v0\.2\.0/ });
    // The installer does everything, so there are no install steps or pre-release warning.
    expect(screen.queryByRole("heading", { name: "Install" })).toBeNull();
    expect(screen.queryByText(/Pre-release/)).toBeNull();

    await userEvent.click(button);
    expect(dialog).toHaveAttribute("open");
    expect(within(dialog).getByText(/reviewed by Windows/)).toBeInTheDocument();
    expect(within(dialog).getByText("AB".repeat(32))).toBeInTheDocument();
    const download = within(dialog).getByRole("link", { name: "Download ForeverTracker-Setup-0.2.0.exe" });
    expect(download).toHaveAttribute("href", url);
    expect(download).toHaveFocus();
    // Dropdowns for the code and the author, next to "Check the file yourself".
    for (const title of ["Check the file yourself", "See the code", "Meet the author"]) {
      expect(within(dialog).getByText(title).tagName).toBe("SUMMARY");
    }
    expect(within(dialog).getByRole("link", { name: "github.com/obelisk2u/ForeverTracker" })).toHaveAttribute("href", REPO_URL);
    expect(within(dialog).getByRole("link", { name: "jordan-stout.com" })).toHaveAttribute("href", AUTHOR_URL);

    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(dialog).not.toHaveAttribute("open");
  });

  it("still explains Windows' warning for a signed installer, naming the publisher", async () => {
    uploaderRelease.mockResolvedValue({ ...release, signed: true });
    render(await DownloadPage());
    await userEvent.click(screen.getByRole("button", { name: /Download for Windows · v0\.2\.0/ }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/ForeverTracker is signed, but it's new/)).toBeInTheDocument();
    expect(within(dialog).getByText("Jordan Stout")).toBeInTheDocument();
    expect(within(dialog).getByRole("link", { name: "Download ForeverTracker-Setup-0.2.0.exe" })).toHaveAttribute("href", url);
  });

  it("has no download button until a release is published", async () => {
    uploaderRelease.mockRejectedValue(new Error("no desktop app release published"));
    render(await DownloadPage());
    expect(screen.queryByRole("button", { name: /Download for Windows/ })).toBeNull();
    expect(screen.queryByRole("link", { name: /Download for Windows/ })).toBeNull();
    expect(screen.getByText(/nonintrusive desktop app/)).toBeInTheDocument();
  });
});

describe("code signing policy", () => {
  it("names the signing service and publisher, how to check a download, and the privacy statement", async () => {
    const { default: CodeSigningPage } = await import("@/app/code-signing/page");
    uploaderRelease.mockResolvedValue({ ...release, signed: false });
    render(await CodeSigningPage());
    expect(screen.getByRole("link", { name: "Azure Artifact Signing" })).toHaveAttribute(
      "href",
      "https://azure.microsoft.com/products/artifact-signing",
    );
    expect(screen.getByText(/Windows shows the publisher as Jordan Stout/)).toBeInTheDocument();
    expect(screen.getByText(/the installer is unsigned/)).toBeInTheDocument();
    expect(screen.getByText(/Digital Signatures tab/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "privacy notice" })).toHaveAttribute("href", "/privacy");
  });

  it("drops the unsigned note once a signed release is out", async () => {
    const { default: CodeSigningPage } = await import("@/app/code-signing/page");
    uploaderRelease.mockResolvedValue({ ...release, signed: true });
    render(await CodeSigningPage());
    expect(screen.queryByText(/the installer is unsigned/)).toBeNull();
  });
});
