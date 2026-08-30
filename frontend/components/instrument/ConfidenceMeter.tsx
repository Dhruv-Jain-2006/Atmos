const SEGMENTS = 5;

type Props = {
  /** 0..1 from the API. Derived from history depth, breadth and consistency. */
  value: number | null | undefined;
  className?: string;
};

/**
 * Segmented confidence readout, deliberately shaped like a signal-strength
 * meter rather than a percentage bar.
 *
 * Confidence is how much the observatory trusts its own reading, and it must be
 * visible next to every number it qualifies. A technology with one day of
 * history and a dramatic momentum value should look obviously under-observed.
 */
export function ConfidenceMeter({ value, className }: Props) {
  const filled = value === null || value === undefined ? 0 : Math.round(value * SEGMENTS);
  const label =
    value === null || value === undefined
      ? "Confidence unknown"
      : `Confidence ${Math.round(value * 100)}%`;

  return (
    <span
      className={`inline-flex items-end gap-[2px] ${className ?? ""}`}
      role="img"
      aria-label={label}
      title={label}
    >
      {Array.from({ length: SEGMENTS }, (_, index) => (
        <span
          key={index}
          className={index < filled ? "st-fill w-[3px] rounded-[1px]" : "w-[3px] rounded-[1px] bg-edge"}
          style={{ height: `${5 + index * 2}px` }}
        />
      ))}
    </span>
  );
}
