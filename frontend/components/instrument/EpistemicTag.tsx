import type { EpistemicStatus } from "@/lib/types";

const MEANING: Record<EpistemicStatus, string> = {
  observation: "Directly measured from ingested source data.",
  inference: "Derived from observations by a deterministic rule.",
  hypothesis: "A candidate explanation, not established.",
  unknown: "Insufficient evidence to characterise.",
};

type Props = {
  status: EpistemicStatus;
  className?: string;
};

/**
 * The epistemic standing of the claim it sits beside.
 *
 * CLAUDE.md requires that observation, inference, hypothesis and unknown are
 * distinguishable. Carrying that only in the JSON is not enough — if the
 * interface renders an inference and a measurement identically, the product is
 * presenting speculation as fact regardless of what the payload said.
 */
export function EpistemicTag({ status, className }: Props) {
  return (
    <span
      data-epistemic={status}
      title={MEANING[status]}
      className={[
        "ep-text ep-edge inline-flex items-center rounded-sm border px-1.5 py-px font-mono text-[9px] uppercase tracking-[0.14em]",
        className ?? "",
      ].join(" ")}
    >
      {status}
    </span>
  );
}
