import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LocalTime } from "@/components/LocalTime";
import { formatDateTime } from "@/lib/format";

// 20:30 UTC on Nov 19 is already Nov 20 in Tokyo and still the afternoon of Nov 19 in Chicago.
const ISO = "2026-11-19T20:30:00Z";

function viewFrom(timeZone: string) {
  const real = Intl.DateTimeFormat.prototype.resolvedOptions;
  vi.spyOn(Intl.DateTimeFormat.prototype, "resolvedOptions").mockImplementation(function (this: Intl.DateTimeFormat) {
    return { ...real.call(this), timeZone };
  });
}

describe("dates in the viewer's timezone", () => {
  afterEach(() => vi.restoreAllMocks());

  it("writes UTC when no zone is given, as the server does", () => {
    expect(formatDateTime(ISO)).toBe("Nov 19, 2026, 08:30 PM UTC");
  });

  it("shows the date and time where the viewer is", () => {
    viewFrom("Asia/Tokyo");
    render(<LocalTime iso={ISO} format="short" />);
    const time = screen.getByText("Nov 20");
    expect(time).toHaveAttribute("dateTime", ISO);
    expect(time.getAttribute("title")).toBe("Nov 20, 2026, 05:30 AM GMT+9");
  });

  it("keeps custom text but puts the local time on hover", () => {
    viewFrom("America/Chicago");
    render(<LocalTime iso={ISO}>+4:07</LocalTime>);
    expect(screen.getByText("+4:07").getAttribute("title")).toBe("Nov 19, 2026, 02:30 PM CST");
  });
});
