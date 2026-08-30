type Props = {
  /** Signed composite in -1..1. Positive means accelerating. */
  value: number;
  width?: number;
  className?: string;
};

/**
 * Signed momentum gauge: fills right of centre when accelerating, left when
 * decaying. A centre-anchored bar is used rather than a 0–100% fill because the
 * sign is the reading — a left-anchored bar would make -0.8 look like a small
 * positive value at a glance.
 */
export function MomentumBar({ value, width = 64, className }: Props) {
  const clamped = Math.max(-1, Math.min(1, value));
  const half = width / 2;
  const extent = Math.abs(clamped) * half;

  return (
    <svg
      width={width}
      height={8}
      viewBox={`0 0 ${width} 8`}
      className={className}
      role="img"
      aria-label={`Momentum ${clamped >= 0 ? "+" : ""}${clamped.toFixed(2)}`}
    >
      <rect x={0} y={3} width={width} height={2} className="fill-edge" rx={1} />
      <rect
        x={clamped >= 0 ? half : half - extent}
        y={2}
        width={Math.max(extent, clamped === 0 ? 0 : 1)}
        height={4}
        rx={1}
        className="st-paint"
      />
      <rect x={half - 0.5} y={0} width={1} height={8} className="fill-edge-lit" />
    </svg>
  );
}
