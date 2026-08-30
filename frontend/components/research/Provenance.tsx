import { EpistemicTag } from "@/components/instrument/EpistemicTag";
import type { DataFreshness, SignalSnapshot } from "@/lib/types";
import { isoDate } from "@/lib/format";

type Props = {
  signals: SignalSnapshot | null | undefined;
  freshness: DataFreshness;
  sensorCount: number;
};

/**
 * "Show me the evidence" — and, just as importantly, show me the limits.
 *
 * Two columns. The left states how the numbers on this page were derived; the
 * right states what this slice cannot establish. The right-hand column is not a
 * disclaimer for legal comfort — under CLAUDE.md's rules an unmeasured thing is
 * an UNKNOWN, and an UNKNOWN that the interface never mentions reads to the user
 * as a settled question.
 */
export function Provenance({ signals, freshness, sensorCount }: Props) {
  const derivation: { label: string; detail: string }[] = [
    {
      label: "Sensor basis",
      detail: `${sensorCount} GitHub repositor${sensorCount === 1 ? "y" : "ies"}, weighted by `
        + "curated relation (canonical > implementation > ecosystem > discovered).",
    },
    {
      label: "Observation window",
      detail: `${signals?.sample_days ?? 0} observed day(s), latest reading ${isoDate(freshness.as_of)}. `
        + "Metrics are polled incrementally; one row per repository per day.",
    },
    {
      label: "Momentum",
      detail: "Normalised −1…+1 composite of star velocity, star acceleration and "
        + "commit/release/contributor activity, measured against this technology's own baseline.",
    },
    {
      label: "Anomaly",
      detail: "Standard deviations from this technology's own trailing distribution — "
        + "scale-free, so a large project is not permanently 'hot' for being large.",
    },
    {
      label: "Weather state",
      detail: "Assigned by a deterministic classifier over the signals above. "
        + "No language model participates in detection or in this page's read path.",
    },
  ];

  const limits: { label: string; detail: string }[] = [
    {
      label: "Single-source risk",
      detail: "Every number here derives from GitHub alone. Package downloads, papers, "
        + "models and CVEs are not yet observed, so adoption outside development is unmeasured.",
    },
    {
      label: "Attention is not adoption",
      detail: "Stars measure attention. A star spike caused by one aggregator post and one "
        + "caused by broad adoption are indistinguishable at this sensor resolution.",
    },
    {
      label: "Causation",
      detail: "Nothing on this page explains why the change happened. Cause requires the "
        + "research engine and external corroboration.",
    },
    ...(signals && signals.sample_days < 7
      ? [
          {
            label: "Under-observed",
            detail: `Only ${signals.sample_days} day(s) of history back this reading. Baselines are `
              + "not yet meaningful and the weather state should be treated as provisional.",
          },
        ]
      : []),
  ];

  return (
    <div className="grid divide-edge/60 lg:grid-cols-2 lg:divide-x">
      <section className="px-4 py-4">
        <h3 className="flex items-center gap-2 font-mono text-[9px] uppercase tracking-[0.16em] text-faint">
          How this was derived
          <EpistemicTag status="observation" />
        </h3>
        <dl className="mt-3 space-y-3">
          {derivation.map((item) => (
            <div key={item.label}>
              <dt className="font-mono text-[10px] uppercase tracking-[0.12em] text-dim">
                {item.label}
              </dt>
              <dd className="mt-0.5 text-[11.5px] leading-relaxed text-faint">{item.detail}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="border-t border-edge/60 px-4 py-4 lg:border-t-0">
        <h3 className="flex items-center gap-2 font-mono text-[9px] uppercase tracking-[0.16em] text-faint">
          What this cannot establish
          <EpistemicTag status="unknown" />
        </h3>
        <dl className="mt-3 space-y-3">
          {limits.map((item) => (
            <div key={item.label}>
              <dt className="font-mono text-[10px] uppercase tracking-[0.12em] text-dim">
                {item.label}
              </dt>
              <dd className="mt-0.5 text-[11.5px] leading-relaxed text-faint">{item.detail}</dd>
            </div>
          ))}
        </dl>
      </section>
    </div>
  );
}
