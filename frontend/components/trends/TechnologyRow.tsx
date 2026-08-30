"use client";

import * as HoverCard from "@radix-ui/react-hover-card";
import Link from "next/link";

import { ConfidenceMeter } from "@/components/instrument/ConfidenceMeter";
import { MomentumBar } from "@/components/instrument/MomentumBar";
import { Sparkline } from "@/components/instrument/Sparkline";
import { IntelligencePreview } from "@/components/trends/IntelligencePreview";
import { compact, signed } from "@/lib/format";
import type { TechnologyCard, Vocabulary } from "@/lib/types";
import { lookup } from "@/lib/vocabulary";

type Props = {
  card: TechnologyCard;
  vocabulary: Vocabulary | null;
  index: number;
};

function observationClass(card: TechnologyCard): string {
  const days = card.signals.sample_days ?? 0;
  if (days < 7) return "coverage-thin";
  if (card.signals.confidence >= 0.6) return "coverage-strong";
  return "coverage-ok";
}

function observationLabel(card: TechnologyCard): string {
  const days = card.signals.sample_days ?? 0;
  if (days < 7) return `${days}d — under-observed`;
  return `${days}d observed`;
}

/**
 * One technology as a ranked instrument row.
 *
 * Rows, not cards: the whole point of Trends is comparison, and a grid of cards
 * makes fifteen technologies impossible to compare on any axis. Aligned columns
 * of monospace digits do it at a glance.
 *
 * The hover preview reads entirely from `card` — no second request. That is why
 * `TechnologyCard` carries its own spark series and explanation.
 */
export function TechnologyRow({ card, vocabulary, index }: Props) {
  const vocab = lookup(vocabulary);
  const glyph = vocab.stateGlyph(card.weather_state);

  return (
    <HoverCard.Root openDelay={90} closeDelay={60}>
      <HoverCard.Trigger asChild>
        <Link
          href={`/research/${card.slug}`}
          data-state={card.weather_state}
          className="scan-in group grid grid-cols-[1.5rem_minmax(0,1fr)_auto] items-center gap-x-2.5 gap-y-0.5 border-b border-edge/60 px-3 py-2 transition-colors last:border-b-0 hover:bg-edge/25 focus-visible:bg-edge/25 focus-visible:outline-none sm:grid-cols-[1.5rem_1.25rem_minmax(0,1fr)_88px_64px_3.5rem_3.25rem_auto] sm:gap-x-3 sm:px-4 sm:py-2.5"
          style={{ animationDelay: `${Math.min(index, 8) * 24}ms` }}
        >
          {/* Rank */}
          <span className="font-mono text-[10px] tabular-nums text-ghost">
            {String(index + 1).padStart(2, "0")}
          </span>

          {/* State glyph */}
          <span aria-hidden className="text-sm leading-none sm:text-[13px]">
            {glyph || <span className="st-fill block size-1.5 rounded-full" />}
          </span>

          {/* Name + subdomain — the dominant signal */}
          <span className="min-w-0">
            <span className="block truncate text-[13.5px] font-medium text-ink group-hover:text-white sm:text-[14px]">
              {card.name}
            </span>
            <span className="block truncate font-mono text-[9px] uppercase tracking-[0.14em] text-faint">
              {vocab.subdomainLabel(card.subdomain)}
            </span>
          </span>

          {/* Sparkline — hidden on smallest screens */}
          <Sparkline
            values={card.spark ?? []}
            state={card.weather_state}
            className="hidden sm:block"
          />

          {/* Momentum bar */}
          <span className="hidden items-center sm:flex">
            <MomentumBar value={card.signals.momentum} />
          </span>

          {/* Stars delta 7d */}
          <span
            className="st-text hidden text-right font-mono text-[11px] tabular-nums sm:block"
            title="Weighted star change over the trailing 7 days"
          >
            {signed(card.signals.stars_delta_7d)}
          </span>

          {/* Total stars */}
          <span
            className="hidden text-right font-mono text-[11px] tabular-nums text-faint sm:block"
            title="Total stars across this technology's repository sensors"
          >
            {compact(card.signals.stars_total)}
          </span>

          {/* Confidence + observation coverage */}
          <span className="hidden justify-end sm:flex">
            <ConfidenceMeter value={card.signals.confidence} />
          </span>

          {/* Mobile: observation days */}
          <span className={`font-mono text-[9px] tabular-nums sm:hidden ${observationClass(card)}`}>
            {card.signals.sample_days ?? 0}d
          </span>
        </Link>
      </HoverCard.Trigger>

      <HoverCard.Portal>
        <HoverCard.Content
          side="right"
          align="start"
          sideOffset={10}
          collisionPadding={16}
          className="preview-panel z-50 w-[320px] sm:w-[340px]"
        >
          <IntelligencePreview card={card} vocabulary={vocabulary} />
          <HoverCard.Arrow className="fill-edge-lit" width={10} height={5} />
        </HoverCard.Content>
      </HoverCard.Portal>
    </HoverCard.Root>
  );
}
