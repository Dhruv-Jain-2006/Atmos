import Link from "next/link";

import { EpistemicTag } from "@/components/instrument/EpistemicTag";
import { NoObservation } from "@/components/instrument/NoObservation";
import { percent } from "@/lib/format";
import type { RelatedTechnology, Vocabulary } from "@/lib/types";
import { lookup } from "@/lib/vocabulary";

type Props = {
  related: readonly RelatedTechnology[];
  vocabulary: Vocabulary | null;
  emptyReason?: string | null;
};

/**
 * "What is connected to it?" — the fourth question in CLAUDE.md's loop.
 *
 * Each edge carries a strength and an epistemic status, and the two are shown
 * together deliberately: a curated relationship is an OBSERVATION about the
 * ecosystem, a co-occurrence edge the detector computed is an INFERENCE, and a
 * graph that renders both identically is a graph that overstates what it knows.
 */
export function RelatedTechnologies({ related, vocabulary, emptyReason }: Props) {
  const vocab = lookup(vocabulary);

  if (related.length === 0) {
    return (
      <NoObservation
        title="No relationships recorded"
        reason={emptyReason ?? undefined}
        hint="Curated edges arrive with the universe; inferred edges need co-occurrence history."
        className="py-12"
      />
    );
  }

  return (
    <ul className="divide-y divide-edge/60">
      {related.map((edge) => (
        <li key={`${edge.relation_type}-${edge.slug}`}>
          <Link
            href={`/research/${edge.slug}`}
            data-state={edge.weather_state ?? undefined}
            className="grid grid-cols-[1.25rem_minmax(0,1fr)_auto] items-center gap-x-3 px-4 py-2.5 transition-colors hover:bg-edge/25 focus-visible:bg-edge/25 focus-visible:outline-none sm:grid-cols-[1.25rem_minmax(0,1fr)_7rem_5rem_auto]"
          >
            <span aria-hidden className="st-text text-center text-[13px] leading-none">
              {edge.weather_state ? vocab.stateGlyph(edge.weather_state) || "◌" : "◌"}
            </span>

            <span className="min-w-0">
              <span className="block truncate text-[12px] text-ink">{edge.name}</span>
              <span className="block truncate font-mono text-[9px] uppercase tracking-[0.12em] text-ghost">
                {vocab.subdomainLabel(edge.subdomain)}
              </span>
            </span>

            <span className="hidden font-mono text-[9px] uppercase tracking-[0.12em] text-faint sm:block">
              {edge.relation_type.replace(/_/g, " ")}
            </span>

            <span
              className="hidden items-center gap-2 sm:flex"
              title={`Edge strength ${percent(edge.strength)}`}
            >
              <span aria-hidden className="h-1 w-10 overflow-hidden rounded-full bg-grid">
                <span
                  className="block h-full bg-signal"
                  style={{ width: `${Math.round(edge.strength * 100)}%` }}
                />
              </span>
              <span className="font-mono text-[10px] tabular-nums text-faint">
                {percent(edge.strength)}
              </span>
            </span>

            <EpistemicTag status={edge.epistemic_status} />
          </Link>
        </li>
      ))}
    </ul>
  );
}
