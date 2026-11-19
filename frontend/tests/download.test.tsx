import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const { uploaderRelease } = vi.hoisted(() => ({ uploaderRelease: vi.fn() }));
vi.mock("@/lib/api", () => ({ api: { uploaderRelease } }));

import DownloadPage from "@/app/download/page";
import { otherSystem } from "@/components/DownloadButton";
import { AUTHOR_URL, CURSEFORGE_URL, REPO_URL } from "@/lib/site";

const url = "https://forevertracker.example/ForeverTracker-Setup-0.2.0.exe";
const release = { version: "0.2.0", download_url: url, sha256: "ab".repeat(32) };

describe("download page", () => {
  it("starts the download straight from the button, with no warning first", async () => {
    uploaderRelease.mockResolvedValue({ ...release, signed: false });
    render(await DownloadPage());
    const download = screen.getByRole("link", { name: /Download for Windows · v0\.2\.0/ });
    expect(download).toHaveAttribute("href", url);
    expect(screen.queryByRole("dialog", { hidden: true })).toBeNull();
    expect(screen.queryByText(/Run anyway/)).toBeNull();
    // The installer does everything, so there are no install steps or pre-release warning.
    expect(screen.queryByRole("heading", { name: "Install" })).toBeNull();
    expect(screen.queryByText(/Pre-release/)).toBeNull();
    // Optional details below the button: the file's hash, the code and the author.
    for (const title of ["Check the file yourself", "See the code", "Meet the author"]) {
      expect(screen.getByText(title).tagName).toBe("SUMMARY");
    }
    expect(screen.getByText("AB".repeat(32))).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "github.com/obelisk2u/ForeverTracker" })).toHaveAttribute("href", REPO_URL);
    expect(screen.getByRole("link", { name: "jordan-stout.com" })).toHaveAttribute("href", AUTHOR_URL);
  });

  it("links a signed installer the same way", async () => {
    uploaderRelease.mockResolvedValue({ ...release, signed: true });
    render(await DownloadPage());
    expect(screen.getByRole("link", { name: /Download for Windows · v0\.2\.0/ })).toHaveAttribute("href", url);
    expect(screen.queryByText(/Run anyway/)).toBeNull();
  });

  it("has no download button until a release is published", async () => {
    uploaderRelease.mockRejectedValue(new Error("no desktop app release published"));
    render(await DownloadPage());
    expect(screen.queryByRole("button", { name: /Download for Windows/ })).toBeNull();
    expect(screen.queryByRole("link", { name: /Download for Windows/ })).toBeNull();
    expect(screen.getByText(/nonintrusive companion app/)).toBeInTheDocument();
    // The addon alone is still on offer.
    expect(screen.getByRole("link", { name: /CurseForge/ })).toHaveAttribute("href", CURSEFORGE_URL);
  });

  it("offers the addon alone on CurseForge first, then the addon with the app", async () => {
    uploaderRelease.mockResolvedValue({ ...release, signed: true });
    render(await DownloadPage());
    const [addonOnly, withApp] = screen.getAllByRole("heading", { level: 2 }).slice(0, 2);
    expect(addonOnly).toHaveTextContent("Just the addon");
    expect(withApp).toHaveTextContent("Addon + companion app (Windows)");
    const curseforge = within(screen.getByRole("region", { name: "Just the addon" })).getByRole("link", {
      name: "Get the addon on CurseForge ↗",
    });
    expect(curseforge).toHaveAttribute("href", CURSEFORGE_URL);
    expect(curseforge).toHaveAttribute("target", "_blank");
    expect(screen.getByText("Opens curseforge.com")).toBeInTheDocument();
    expect(
      within(screen.getByRole("region", { name: "Addon + companion app (Windows)" })).getByRole("link", {
        name: /Download for Windows/,
      }),
    ).toBeInTheDocument();
  });
});

describe("visitors not on Windows", () => {
  it("are told the app is Windows-only", () => {
    const mac = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15";
    const windows = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36";
    expect(otherSystem(mac)).toBe("a Mac");
    expect(otherSystem("Mozilla/5.0 (X11; Linux x86_64) Firefox/140.0")).toBe("this device");
    expect(otherSystem(windows)).toBeNull();
  });

  it("see the note above the download button on a Mac", async () => {
    const ua = vi.spyOn(navigator, "userAgent", "get").mockReturnValue("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6)");
    uploaderRelease.mockResolvedValue({ ...release, signed: true });
    render(await DownloadPage());
    expect(await screen.findByText(/won.t run on a Mac/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Download for Windows/ })).toBeInTheDocument();
    ua.mockRestore();
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
