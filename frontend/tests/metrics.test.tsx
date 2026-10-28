import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Freshness } from "@/components/Freshness";
import { MetricValue } from "@/components/MetricValue";
import { StatGrid } from "@/components/StatGrid";
import { formatDuration, formatNumber, relativeTime } from "@/lib/format";
import type { MetricOut } from "@/lib/types";

const base: MetricOut = {
  metric: "deaths",
  value: 2,
  unit: "count",
  source: "native_damage_meter",
  status: "observed",
  coverage: "complete_session",
  resolution: "single_source",
  confidence: "medium",
  contributors: 1,
  derived: false,
};

describe("MetricValue", () => {
  it("never renders an unavailable value as zero", () => {
    const { container } = render(<MetricValue metric={{ ...base, value: null, status: "unavailable" }} />);
    expect(container.textContent).not.toContain("0");
    expect(container.textContent).toContain("—");
    expect(screen.getByText("unavailable")).toBeInTheDocument();
  });

  it("distinguishes 'not observed' from 'unavailable'", () => {
    render(<MetricValue metric={undefined} />);
    expect(screen.getByText("not observed")).toBeInTheDocument();
  });

  it("shows a real zero when zero was observed", () => {
    const { container } = render(<MetricValue metric={{ ...base, value: 0 }} />);
    expect(container.textContent).toContain("0");
  });

  it("marks partial coverage, disagreement and corroboration", () => {
    render(<MetricValue metric={{ ...base, coverage: "partial_session", status: "incomplete" }} />);
    expect(screen.getByLabelText("partial coverage")).toBeInTheDocument();
    render(<MetricValue metric={{ ...base, resolution: "conflicted" }} />);
    expect(screen.getByLabelText("observers disagree")).toBeInTheDocument();
    render(<MetricValue metric={{ ...base, resolution: "corroborated" }} />);
    expect(screen.getByLabelText("corroborated")).toBeInTheDocument();
  });

  it("explains provenance in the tooltip", () => {
    const { container } = render(<MetricValue metric={{ ...base, metric: "dps", unit: "per_second", value: 812.5, derived: true }} />);
    const title = container.querySelector("[title]")?.getAttribute("title") ?? "";
    expect(title).toContain("Blizzard damage meter");
    expect(title).toContain("Coverage: complete session");
    expect(title).toContain("Derived");
    expect(container.textContent).toContain("812.5");
  });
});

describe("formatting", () => {
  const now = new Date("2026-10-26T12:00:00Z");
  it("formats relative times", () => {
    expect(relativeTime("2026-10-26T11:59:30Z", now)).toBe("just now");
    expect(relativeTime("2026-10-26T10:00:00Z", now)).toBe("2 h ago");
    expect(relativeTime("2026-10-23T12:00:00Z", now)).toBe("3 days ago");
  });
  it("formats durations and numbers", () => {
    expect(formatDuration(1830)).toBe("30m 30s");
    expect(formatDuration(3720)).toBe("1h 02m");
    expect(formatDuration(null)).toBe("—");
    expect(formatNumber(195000, "amount")).toBe("195K");
    expect(formatNumber(3, "count")).toBe("3");
    expect(formatNumber(780, "per_second")).toBe("780");
  });
});

describe("Freshness", () => {
  it("shows how old the data is with the exact time available", () => {
    render(<Freshness iso="2026-10-23T12:00:00Z" now={new Date("2026-10-26T12:00:00Z")} />);
    const time = screen.getByText("3 days ago");
    expect(time.tagName).toBe("TIME");
    expect(time).toHaveAttribute("dateTime", "2026-10-23T12:00:00Z");
    expect(time.getAttribute("title")).toContain("2026");
  });
});

describe("StatGrid", () => {
  it("shows sample sizes and exclusions, and blanks for insufficient samples", () => {
    render(
      <StatGrid
        stats={{
          runs_observed: { definition: "runs_observed.v1", value: 4, sample_size: 4, excluded: 0, exclusion_reasons: {}, note: null },
          deaths_per_run_mean: {
            definition: "deaths_per_run_mean.v1",
            value: 1,
            sample_size: 3,
            excluded: 1,
            exclusion_reasons: { incomplete_coverage: 1 },
            note: null,
          },
          dps_median: { definition: "dps_median.v1", value: null, sample_size: 0, excluded: 4, exclusion_reasons: {}, note: "insufficient_sample" },
        }}
      />,
    );
    expect(screen.getByText("1.00")).toBeInTheDocument();
    expect(screen.getByText("Based on 3 runs")).toBeInTheDocument();
    expect(screen.getByText("Excluded: 1 incomplete coverage")).toBeInTheDocument();
    expect(screen.getAllByText("Not enough eligible runs").length).toBeGreaterThan(0);
  });
});
