import { Panel } from "@/components/instrument/Panel";
import { signed } from "@/lib/format";
import type { SubdomainClimate, Vocabulary } from "@/lib/types";
import { lookup } from "@/lib/vocabulary";

type Props = {
  climates: readonly SubdomainClimate[];
  vocabulary: Vocabulary | null;
};

/**
 * Per-subdomain regional readout — the radar's sector strip.
 *
 * Ecosystem-wide mean momentum hides the interesting case: agentic tooling
 * accelerating while MLOps cools averages out to "stable". Sector cells keep
 * that visible.
 *
 * Subdomains with no computed signal render as unlit cells rather than being
 * omitted, so the shape of the universe stays constant and a gap reads as "not
 * observed" instead of "does not exist".
 */
export function ClimateStrip({ climates, vocabulary }: Props) {
  const vocab = lookup(vocabulary);

  return (
    <Panel title="Sectors" caption="Weather by subdomain">
      <div className="grid grid-cols-2 divide-edge/60 sm:grid-cols-4 lg:grid-cols-7 lg:divide-x">
        {climates.length === 0 ? (
          <p className="col-span-full px-4 py-6 font-mono text-[11px] uppercase tracking-[0.16em] text-ghost">
            No sector readings
          </p>
        ) : (
          climates.map((climate) => {
            const lit = climate.technology_count > 0;
            const label = climate.label || vocab.subdomainLabel(climate.subdomain);
            return (
              <div
                key={climate.subdomain}
                data-state={climate.dominant_state}
                className="border-b border-edge/60 px-3 py-3 sm:px-4 sm:py-3.5 lg:border-b-0"
              >
                <p
                  className="font-mono text-[9px] uppercase tracking-[0.14em] text-faint"
                  title={label}
                >
                  <span className="hidden sm:inline">{label}</span>
                  <span className="sm:hidden">
                    {label.length > 12 ? `${label.slice(0, 12)}…` : label}
                  </span>
                </p>

                <div className="mt-1.5 flex items-center gap-1.5 sm:mt-2 sm:gap-2">
                  <span aria-hidden className={lit ? "text-base leading-none" : "opacity-30"}>
                    {vocab.stateGlyph(climate.dominant_state) || "◌"}
                  </span>
                  <span
                    className={[
                      "font-mono text-[11px] tabular-nums",
                      lit ? "st-text" : "text-ghost",
                    ].join(" ")}
                  >
                    {lit ? signed(climate.mean_momentum, 2) : "—"}
                  </span>
                </div>

                <p className="mt-1 font-mono text-[9px] uppercase tracking-[0.1em] text-ghost sm:mt-1.5">
                  {climate.technology_count} tracked
                </p>
              </div>
            );
          })
        )}
      </div>
    </Panel>
  );
}
