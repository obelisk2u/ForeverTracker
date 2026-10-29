import { formatNumber } from "@/lib/format";
import { RESOLUTION_LABEL, SOURCE_LABEL } from "@/lib/game";
import type { MetricOut } from "@/lib/types";

// Never renders an unavailable or missing metric as 0. Every value carries its provenance in
// the tooltip, and a visible mark for partial coverage or disagreement.
export function MetricValue({ metric, showMarks = true }: { metric: MetricOut | null | undefined; showMarks?: boolean }) {
  if (!metric || metric.value === null || metric.value === undefined || metric.status === "unavailable") {
    return (
      <span className="text-faint" title={metric ? "Unavailable: the game client did not expose this value" : "Not observed"}>
        —<span className="sr-only">{metric ? "unavailable" : "not observed"}</span>
      </span>
    );
  }
  const partial = metric.coverage !== "complete_session" || metric.status !== "observed";
  const conflicted = metric.resolution === "conflicted";
  const title = [
    `Source: ${SOURCE_LABEL[metric.source] ?? metric.source}`,
    `Status: ${metric.status}`,
    `Coverage: ${metric.coverage.replace("_", " ")}`,
    RESOLUTION_LABEL[metric.resolution] ?? metric.resolution,
    `Confidence: ${metric.confidence}`,
    metric.derived ? "Derived: total ÷ damage-meter combat seconds" : null,
  ]
    .filter(Boolean)
    .join("\n");
  return (
    <span title={title} className="tabular inline-flex items-baseline gap-1">
      <span className={partial ? "text-muted" : undefined}>{formatNumber(metric.value, metric.unit)}</span>
      {showMarks && partial && (
        <span className="text-warn text-xs" aria-label="partial coverage">
          ◐
        </span>
      )}
      {showMarks && conflicted && (
        <span className="text-bad text-xs" aria-label="observers disagree">
          ⚠
        </span>
      )}
      {showMarks && metric.resolution === "corroborated" && (
        <span className="text-good text-xs" aria-label="corroborated">
          ✓
        </span>
      )}
    </span>
  );
}
