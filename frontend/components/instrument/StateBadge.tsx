import type { WeatherState } from "@/lib/types";
import type { VocabularyLookup } from "@/lib/vocabulary";

type Props = {
  state: WeatherState;
  vocabulary: VocabularyLookup;
  size?: "sm" | "md";
  showLabel?: boolean;
  className?: string;
};

/**
 * Weather-state chip.
 *
 * The glyph and label come from `/api/vocabulary`, never from this file — the
 * classifier owns the vocabulary. If the API is unreachable the glyph is simply
 * absent and the key is shown instead.
 */
export function StateBadge({
  state,
  vocabulary,
  size = "md",
  showLabel = true,
  className,
}: Props) {
  const glyph = vocabulary.stateGlyph(state);
  const label = vocabulary.stateLabel(state);
  const meaning = vocabulary.stateMeaning(state);
  const compact = size === "sm";

  return (
    <span
      data-state={state}
      title={meaning || label}
      className={[
        "st-wash st-edge st-text inline-flex items-center gap-1.5 rounded border font-mono uppercase tracking-[0.08em]",
        compact ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-1 text-[11px]",
        className ?? "",
      ].join(" ")}
    >
      {glyph ? (
        <span aria-hidden className={compact ? "text-[11px]" : "text-xs"}>
          {glyph}
        </span>
      ) : null}
      {showLabel ? label : <span className="sr-only">{label}</span>}
    </span>
  );
}
