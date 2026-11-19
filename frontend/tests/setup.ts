import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => cleanup());

vi.mock("next/navigation", () => {
  const push = vi.fn();
  return {
    useRouter: () => ({ push, replace: vi.fn(), prefetch: vi.fn(), back: vi.fn() }),
    useSearchParams: () => new URLSearchParams(),
    usePathname: () => "/",
    notFound: () => {
      throw new Error("NEXT_NOT_FOUND");
    },
    redirect: (url: string) => {
      throw new Error(`NEXT_REDIRECT ${url}`);
    },
    __push: push,
  };
});

// jsdom has no ResizeObserver, which Radix uses to place an open tooltip.
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

// jsdom has <dialog> but not its methods.
HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) {
  this.open = true;
};
HTMLDialogElement.prototype.close ??= function (this: HTMLDialogElement) {
  this.open = false;
};
