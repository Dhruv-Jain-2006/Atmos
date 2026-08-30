"use client";

import { ConfidenceMeter } from "@/components/instrument/ConfidenceMeter";
import { EpistemicTag } from "@/components/instrument/EpistemicTag";
import { MomentumBar } from "@/components/instrument/MomentumBar";
import { Readout } from "@/components/instrument/Panel";
import { Sparkline } from "@/components/instrument/Sparkline";
import { StateBadge } from "@/components/instrument/StateBadge";
import { NO_VALUE, decimal, isoDate, percent, sigma, signed } from "@/lib/format";
import type { TechnologyCard, Vocabulary } from "@/lib/types";
import { lookup } from "@/lib/vocabulary";

type Props = {
  card: TechnologyCard;
  vocabulary: Vocabulary | null;
};

function coverageStatus(card: TechnologyCard): {
  label: string;
  hint: string;
  tone: string;
} {
  const days = card.signals.sample_days ?? 0;
  const confidence = card.signals.confidence ?? 0;
  if (days < 7) {
    return {
      label: "Under-observed",
      hint: `${days}d observed — ${7 - days} more needed before classifying`,
      tone: "text-faint",
    };
  }
  if (confidence >= 0.6) {
    return {
      label: "Sufficient evidence",
      hint: `${days}d observed · ${Math.round(confidence * 100)}% confidence`,
      tone: "text-dim",
    };
  }
  return {
    label: "Weak evidence",
    hint: `${days}d observed · low confidence — interpret with caution`,
    tone: "text-faint",
  };
}

/**
 * Compact intelligence preview shown on hover.
 *
 * This is the product's first real interaction, so it has to answer more than
 * "what is this": the weather state, how fast it is moving, how much the
 * observatory trusts the reading, and one sentence of why.
 *
 * Everything rendered here is already on the `TechnologyCard`. No fetch, no
 * loading state, no spinner on hover — a preview that has to load is not a
 * preview.
 */
export function IntelligencePreview({ card, vocabulary }: Props) {
  const vocab = lookup(vocabulary);
  const signals = card.signals;
  const coverage = coverageStatus(card);

  return (
    <div
      data-state={card.weather_state}
      className="st-glow border border-edge-lit bg-deep/95 shadow-2xl backdrop-blur-sm"
    >
      {/* Header — name, subdomain, state badge */}
      <div className="flex items-start justify-between gap-3 border-b border-edge px-3.5 py-3">
        <div className="min-w-0">
          <p className="truncate text-[14px] font-medium text-ink">{card.name}</p>
          <p className="font-mono text-[9px] uppercase tracking-[0.16em] text-faint">
            {vocab.subdomainLabel(card.subdomain)}
            {card.as_of ? ` · ${isoDate(card.as_of)}` : ""}
          </p>
        </div>
        <StateBadge state={card.weather_state} vocabulary={vocab} size="sm" />
      </div>

      {/* Explanation — why the classifier chose this state */}
      {card.explanation ? (
        <p className="border-b border-edge px-3.5 py-3 text-[12px] leading-relaxed text-dim">
          {card.explanation}
        </p>
      ) : null}

      {/* Sparkline with observation context */}
      <div className="flex items-center gap-3 border-b border-edge px-3.5 py-2.5">
        <Sparkline
          values={card.spark ?? []}
          state={card.weather_state}
          width={248}
          height={30}
        />
        <span className="font-mono text-[9px] uppercase tracking-[0.12em] text-faint">
          {card.spark?.length ? `${card.spark.length}d trace` : "no trace"}
        </span>
      </div>

      {/* Primary signals — momentum, confidence, anomaly */}
      <div className="grid grid-cols-3 gap-x-3 gap-y-3 px-3.5 py-3">
        <Readout
          label="Momentum"
          value={
            <span className="flex items-center gap-1.5">
              <span className="st-text">{signed(signals.momentum, 2)}</span>
              <MomentumBar value={signals.momentum} width={34} />
            </span>
          }
          hint="Normalised -1..1 composite of star acceleration, anomaly and activity"
        />
        <Readout
          label="Confidence"
          value={
            <span className="flex items-center gap-1.5">
              {percent(signals.confidence)}
              <ConfidenceMeter value={signals.confidence} />
            </span>
          }
          hint="History depth, sensor breadth and consistency"
        />
        <Readout
          label="Anomaly"
          value={sigma(signals.anomaly_z)}
          hint="Deviation from this technology's own baseline, not from other technologies"
        />

        <Readout label="Δ stars 7d" value={signed(signals.stars_delta_7d)} />
        <Readout label="Δ stars 28d" value={signed(signals.stars_delta_28d)} />
        <Readout
          label="Velocity"
          value={
            signals.star_velocity_7d === null || signals.star_velocity_7d === undefined
              ? NO_VALUE
              : `${decimal(signals.star_velocity_7d, 1)}/d`
          }
          hint="Weighted stars per day over the trailing 7 days"
        />

        <Readout
          label="Sensors"
          value={`${signals.active_repo_count ?? 0}/${signals.repo_count ?? 0}`}
          hint="Repositories with activity in the last 7 days, of those tracked"
        />
        <Readout label="Commits/d" value={decimal(signals.commit_velocity_7d, 1)} />
        <Readout
          label="Observed"
          value={`${signals.sample_days ?? 0}d`}
          hint="Days of observation backing this reading"
        />
      </div>

      {/* Footer — observation status, epistemic standing, action */}
      <div className="flex items-center justify-between gap-2 border-t border-edge px-3.5 py-2.5">
        <div className="flex items-center gap-2.5">
          <EpistemicTag status={card.epistemic_status} />
          <span
            className={`font-mono text-[9px] uppercase tracking-[0.12em] ${coverage.tone}`}
            title={coverage.hint}
          >
            {coverage.label}
          </span>
        </div>
        <span className="font-mono text-[9px] uppercase tracking-[0.14em] text-signal">
          investigate →
        </span>
      </div>
    </div>
  );
}
