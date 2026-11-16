import { formatNumber } from "@/lib/format";
import { RESOLUTION_LABEL, SOURCE_LABEL } from "@/lib/game";
import type { MetricOut } from "@/lib/types";

// Never renders an unavailable or missing metric as 0. Only the number shows; its provenance
// (coverage, disagreement, confidence) is in the hover text.
export function MetricValue({ metric }: { metric: MetricOut | null | undefined }) {
  if (!metric || metric.value === null || metric.value === undefined || metric.status === "unavailable") {
    return (
      <span className="text-faint" title={metric ? "Unavailable: the game client did not expose this value" : "Not observed"}>
        —<span className="sr-only">{metric ? "unavailable" : "not observed"}</span>
      </span>
    );
  }
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
    <span title={title} className="tabular">
      {formatNumber(metric.value, metric.unit)}
    </span>
  );
}
