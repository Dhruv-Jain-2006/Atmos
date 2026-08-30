import { MomentumBar } from "@/components/instrument/MomentumBar";
import { NoObservation } from "@/components/instrument/NoObservation";
import { Readout } from "@/components/instrument/Panel";
import { isoDate, signed } from "@/lib/format";
import type { DataFreshness, Vocabulary, WeatherOverview, WeatherState } from "@/lib/types";
import { STATE_ORDER, lookup } from "@/lib/vocabulary";

type Props = {
  overview: WeatherOverview | null;
  freshness: DataFreshness | null;
  vocabulary: Vocabulary | null;
  transportError?: string | null;
};

function dominantState(counts: Record<string, number> | undefined): WeatherState | null {
  if (!counts) return null;
  let best: WeatherState | null = null;
  let bestCount = 0;
  for (const state of STATE_ORDER) {
    const count = counts[state] ?? 0;
    if (count > bestCount) {
      best = state;
      bestCount = count;
    }
  }
  return best;
}

function momentumInterpretation(momentum: number | null | undefined): string {
  if (momentum === null || momentum === undefined) return "";
  const abs = Math.abs(momentum);
  if (abs < 0.05) return "Activity is consistent with its own recent baseline.";
  if (momentum > 0) {
    if (abs > 0.3) return "Ecosystem is accelerating — strongest signals are gaining momentum.";
    return "Mildly positive momentum — activity is trending upward.";
  }
  if (abs > 0.3) return "Ecosystem is cooling — activity is decelerating across signals.";
  return "Mildly negative momentum — activity is trending downward.";
}

/**
 * The station readout: one glance at the state of the whole ecosystem.
 *
 * Answers CLAUDE.md's first question — "what is changing in AI engineering right
 * now?" — before any scrolling. The radar sweep behind it is not decoration: it
 * runs whenever the observatory has data, and stops when it does not.
 */
export function StationHeader({ overview, freshness, vocabulary, transportError }: Props) {
  const vocab = lookup(vocabulary);
  const hasData = Boolean(freshness?.has_data && overview);
  const counts = (overview?.state_counts ?? undefined) as Record<string, number> | undefined;
  const dominant = dominantState(counts);
  const total = counts ? Object.values(counts).reduce((sum, n) => sum + n, 0) : 0;

  return (
    <section className="relative overflow-hidden border border-edge bg-panel/50">
      {hasData ? <div className="radar-sweep opacity-60" aria-hidden /> : null}

      <div className="relative">
        <header className="flex flex-wrap items-baseline justify-between gap-3 border-b border-edge px-5 py-2.5">
          <h1 className="font-mono text-[11px] uppercase tracking-[0.28em] text-dim">
            Global conditions
          </h1>
          <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-faint">
            AI engineering · {isoDate(freshness?.as_of)}
          </p>
        </header>

        {hasData && dominant ? (
          <>
            <div className="flex flex-wrap items-start justify-between gap-6 px-5 py-6 sm:items-end sm:gap-8 sm:py-7">
              <div data-state={dominant} className="flex items-center gap-4 sm:gap-5">
                <span aria-hidden className="st-text text-4xl leading-none sm:text-5xl">
                  {vocab.stateGlyph(dominant) || "◍"}
                </span>
                <div>
                  <p className="st-text text-2xl leading-tight font-medium tracking-tight sm:text-3xl">
                    {vocab.stateLabel(dominant)}
                  </p>
                  <p className="mt-1 max-w-sm text-[12px] leading-relaxed text-faint sm:text-[13px]">
                    {vocab.stateMeaning(dominant)}
                  </p>
                </div>
              </div>

              <div className="flex flex-wrap items-end gap-x-6 gap-y-3 sm:gap-x-8 sm:gap-y-4">
                <div data-state={dominant}>
                  <Readout
                    label="Momentum"
                    value={
                      <span className="flex items-baseline gap-2">
                        <span className="st-text">{signed(overview?.mean_momentum, 3)}</span>
                        <MomentumBar value={overview?.mean_momentum ?? 0} width={52} />
                      </span>
                    }
                    emphasis
                    hint="Average signed momentum across every tracked technology"
                  />
                </div>
                <Readout
                  label="Technologies"
                  value={overview?.technology_count ?? 0}
                  emphasis
                  hint="Technologies with a computed signal on this day"
                />
                <Readout
                  label="Observed"
                  value={`${freshness?.observed_days ?? 0}d`}
                  emphasis
                  hint="Distinct days of observation behind these signals"
                />
              </div>
            </div>

            {/* Interpretive sentence — connects momentum to state for the first-time visitor */}
            <div className="border-t border-edge px-5 py-2.5">
              <p className="font-mono text-[11px] leading-relaxed text-dim">
                {momentumInterpretation(overview?.mean_momentum)}
              </p>
            </div>

            {total > 0 ? (
              <div className="border-t border-edge px-5 py-3">
                <div className="flex h-1.5 w-full overflow-hidden rounded-full bg-grid">
                  {STATE_ORDER.map((state) => {
                    const count = counts?.[state] ?? 0;
                    if (count === 0) return null;
                    return (
                      <span
                        key={state}
                        data-state={state}
                        className="st-fill h-full"
                        style={{ width: `${(count / total) * 100}%` }}
                        title={`${vocab.stateLabel(state)}: ${count}`}
                      />
                    );
                  })}
                </div>
                <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
                  {STATE_ORDER.map((state) => {
                    const count = counts?.[state] ?? 0;
                    return (
                      <li
                        key={state}
                        data-state={state}
                        className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.1em]"
                      >
                        <span
                          className={count > 0 ? "st-fill size-1.5 rounded-full" : "size-1.5 rounded-full bg-ghost"}
                          aria-hidden
                        />
                        <span className={count > 0 ? "text-dim" : "text-ghost"}>
                          {vocab.stateLabel(state)}
                        </span>
                        <span className="tabular-nums text-faint">{count}</span>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ) : null}
          </>
        ) : (
          <NoObservation
            reason={transportError ?? freshness?.degraded_reason ?? null}
            hint={
              transportError
                ? "API unreachable — check the backend connection."
                : "Run the bootstrap worker to seed the universe and take the first reading."
            }
          />
        )}
      </div>
    </section>
  );
}
