import { formatDuration, formatRate, percent } from "@/lib/format";
import type { StatValue } from "@/lib/types";

const REASONS: Record<string, string> = {
  incomplete_coverage: "incomplete coverage",
  metric_unavailable: "not available",
  partial_presence: "joined late or left early",
  run_in_progress: "still in progress",
  ineligible: "ineligible",
};

function describeExclusions(stat: StatValue): string | null {
  const parts = Object.entries(stat.exclusion_reasons ?? {}).map(([k, n]) => `${n} ${REASONS[k] ?? k}`);
  return parts.length ? `Excluded: ${parts.join(", ")}` : null;
}

function StatCard({
  label,
  stat,
  format,
  help,
}: {
  label: string;
  stat: StatValue | undefined;
  format: (v: number) => string;
  help: string;
}) {
  const value = stat?.value;
  const exclusions = stat ? describeExclusions(stat) : null;
  return (
    <div className="card p-4 flex flex-col gap-1" title={help}>
      <span className="text-xs uppercase tracking-wide text-faint">{label}</span>
      <span className="text-2xl font-semibold tabular text-text">
        {value === null || value === undefined ? <span className="text-faint">—</span> : format(value)}
      </span>
      <span className="text-xs text-faint">
        {stat ? (
          <>
            {stat.note === "insufficient_sample" ? "Not enough eligible runs" : `Based on ${stat.sample_size} run${stat.sample_size === 1 ? "" : "s"}`}
            {exclusions && <span className="block">{exclusions}</span>}
          </>
        ) : (
          "No data"
        )}
      </span>
    </div>
  );
}

export function StatGrid({ stats }: { stats: Record<string, unknown> }) {
  const s = stats as Record<string, StatValue>;
  const count = (v: number) => String(Math.round(v));
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <StatCard label="Observed runs" stat={s.runs_observed} format={count} help="Dungeon runs in which this character was observed by a ForeverTracker user." />
      <StatCard
        label="Confirmed completions"
        stat={s.completions_confirmed}
        format={count}
        help="Runs with an in-game completion event while this character was still in the group."
      />
      <StatCard
        label="Deaths per run"
        stat={s.deaths_per_run_mean}
        format={(v) => v.toFixed(2)}
        help="Mean deaths over runs with complete death coverage and at least 90% presence. Partially observed runs are excluded, never counted as zero."
      />
      <StatCard label="Death-free runs" stat={s.death_free_run_pct} format={(v) => percent(v)} help="Share of fully covered runs without a death." />
      <StatCard label="Median DPS" stat={s.dps_median} format={formatRate} help="Median of per-run damage ÷ damage-meter combat seconds, fully covered runs, non-healer roles." />
      <StatCard label="Median HPS" stat={s.hps_median} format={formatRate} help="Median of per-run healing ÷ combat seconds, healer role, fully covered runs." />
      <StatCard label="Interrupts per run" stat={s.interrupts_per_run_mean} format={(v) => v.toFixed(1)} help="Mean native-meter interrupts over fully covered runs." />
      <StatCard
        label="Avg. completion time"
        stat={s.completed_run_duration_mean}
        format={(v) => formatDuration(v)}
        help="Mean duration of confirmed completions the character was present for."
      />
    </div>
  );
}
