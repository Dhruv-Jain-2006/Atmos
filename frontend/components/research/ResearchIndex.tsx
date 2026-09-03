"use client";

import Link from "next/link";
import { useCallback, useMemo, useState } from "react";

import { ConfidenceMeter } from "@/components/instrument/ConfidenceMeter";
import { MomentumBar } from "@/components/instrument/MomentumBar";
import { NoObservation } from "@/components/instrument/NoObservation";
import { StateBadge } from "@/components/instrument/StateBadge";
import { compact, signed, isoDate } from "@/lib/format";
import type { TechnologyCard, Vocabulary } from "@/lib/types";
import { lookup } from "@/lib/vocabulary";

type Props = {
  items: TechnologyCard[];
  vocabulary: Vocabulary | null;
};

function sortTechnologies(items: TechnologyCard[]): TechnologyCard[] {
  return [...items].sort((a, b) => {
    // Headline technologies first
    if (a.headline !== b.headline) return a.headline ? -1 : 1;
    // Then absolute momentum descending
    const aMom = Math.abs(a.signals.momentum);
    const bMom = Math.abs(b.signals.momentum);
    if (aMom !== bMom) return bMom - aMom;
    // Then confidence descending
    if (a.signals.confidence !== b.signals.confidence) {
      return b.signals.confidence - a.signals.confidence;
    }
    // Then alphabetical
    return a.name.localeCompare(b.name);
  });
}

export function ResearchIndex({ items, vocabulary }: Props) {
  const [query, setQuery] = useState("");
  const vocab = lookup(vocabulary);

  const sorted = useMemo(() => sortTechnologies(items), [items]);

  const filtered = useMemo(() => {
    if (!query.trim()) return sorted;
    const q = query.toLowerCase();
    return sorted.filter((t) => {
      if (t.name.toLowerCase().includes(q)) return true;
      if (t.slug.toLowerCase().includes(q)) return true;
      if (vocab.subdomainLabel(t.subdomain).toLowerCase().includes(q)) return true;
      return false;
    });
  }, [sorted, query, vocab]);

  const handleSearch = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => setQuery(e.target.value),
    [],
  );

  if (items.length === 0) {
    return (
      <NoObservation
        title="No technologies currently observed"
        hint="Technologies appear after the universe is seeded and the first ingestion run completes."
      />
    );
  }

  return (
    <div>
      {/* Search */}
      <div className="border-b border-edge px-4 py-3 sm:px-5">
        <label htmlFor="research-search" className="sr-only">
          Search technologies
        </label>
        <div className="relative">
          <input
            id="research-search"
            type="search"
            value={query}
            onChange={handleSearch}
            placeholder="Search technologies\u2026"
            className="w-full rounded-sm border border-edge bg-deep/60 px-3 py-1.5 font-mono text-[11px] text-ink placeholder:text-ghost focus:border-edge-lit focus:outline-none"
          />
          {query ? (
            <button
              type="button"
              onClick={() => setQuery("")}
              className="absolute right-2 top-1/2 -translate-y-1/2 font-mono text-[10px] text-ghost hover:text-dim"
              aria-label="Clear search"
            >
              clear
            </button>
          ) : null}
        </div>
      </div>

      {/* Results count */}
      <div className="border-b border-edge/60 px-4 py-2 sm:px-5">
        <p className="font-mono text-[9px] uppercase tracking-[0.14em] text-ghost">
          {filtered.length === items.length
            ? `${items.length} technologies`
            : `${filtered.length} of ${items.length} technologies`}
        </p>
      </div>

      {/* List */}
      {filtered.length === 0 ? (
        <NoObservation
          title="No technologies match this query"
          hint="Try a different search term."
        />
      ) : (
        <ol>
          {filtered.map((tech) => (
            <li key={tech.slug}>
              <Link
                href={`/research/${tech.slug}`}
                data-state={tech.weather_state}
                className="group block border-b border-edge/60 px-4 py-3 transition-colors last:border-b-0 hover:bg-edge/20 focus-visible:bg-edge/20 focus-visible:outline-none sm:px-5 sm:py-3.5"
              >
                {/* Row 1: Name + state */}
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <span className="block truncate text-[13px] font-medium text-ink group-hover:text-white sm:text-[14px]">
                      {tech.name}
                    </span>
                    <span className="block truncate font-mono text-[9px] uppercase tracking-[0.14em] text-faint">
                      {vocab.subdomainLabel(tech.subdomain)} · {tech.slug}
                    </span>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    {tech.headline ? (
                      <span className="rounded-sm border border-edge-lit px-1.5 py-px font-mono text-[8px] uppercase tracking-[0.14em] text-faint">
                        headline
                      </span>
                    ) : null}
                    <StateBadge state={tech.weather_state} vocabulary={vocab} size="sm" />
                  </div>
                </div>

                {/* Row 2: Signals */}
                <div className="mt-2 flex flex-wrap items-center gap-x-5 gap-y-1.5">
                  {/* Momentum */}
                  <span className="flex items-center gap-1.5">
                    <span className="font-mono text-[9px] uppercase tracking-[0.12em] text-ghost">
                      mom
                    </span>
                    <span className="st-text font-mono text-[11px] tabular-nums">
                      {signed(tech.signals.momentum, 3)}
                    </span>
                    <MomentumBar value={tech.signals.momentum} width={36} />
                  </span>

                  {/* Confidence */}
                  <span className="flex items-center gap-1.5">
                    <span className="font-mono text-[9px] uppercase tracking-[0.12em] text-ghost">
                      conf
                    </span>
                    <span className="font-mono text-[11px] tabular-nums text-dim">
                      {tech.signals.confidence === 0
                        ? "\u2014"
                        : `${Math.round(tech.signals.confidence * 100)}%`}
                    </span>
                    <ConfidenceMeter value={tech.signals.confidence} />
                  </span>

                  {/* Stars */}
                  <span className="hidden items-center gap-1.5 sm:flex">
                    <span className="font-mono text-[9px] uppercase tracking-[0.12em] text-ghost">
                      stars
                    </span>
                    <span className="font-mono text-[11px] tabular-nums text-faint">
                      {compact(tech.signals.stars_total)}
                    </span>
                  </span>

                  {/* Observation date */}
                  {tech.as_of ? (
                    <span className="hidden items-center gap-1.5 sm:flex">
                      <span className="font-mono text-[9px] uppercase tracking-[0.12em] text-ghost">
                        observed
                      </span>
                      <span className="font-mono text-[10px] tabular-nums text-faint">
                        {isoDate(tech.as_of)}
                      </span>
                    </span>
                  ) : null}
                </div>

                {/* Row 3: Summary (if available) */}
                {tech.summary ? (
                  <p className="mt-1.5 line-clamp-1 text-[11px] leading-relaxed text-ghost">
                    {tech.summary}
                  </p>
                ) : null}
              </Link>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
