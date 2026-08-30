import type { WeatherState } from "@/lib/types";

type Props = {
  /** Trailing daily momentum, oldest first. Bounded to -1..1 by the classifier. */
  values: readonly number[];
  state: WeatherState;
  width?: number;
  height?: number;
  className?: string;
};

/**
 * Inline momentum trace with a zero baseline.
 *
 * The baseline is the point of the chart: momentum is signed, so "above the
 * line" and "below the line" carry the meaning. A single observation cannot form
 * a trace, so it renders as a mark on the baseline rather than a fabricated
 * flat line suggesting a stable history we never observed.
 *
 * `data-state` is set on the svg itself rather than inherited from a row, so the
 * trace is correctly coloured wherever it is placed.
 */
export function Sparkline({ values, state, width = 88, height = 22, className }: Props) {
  const mid = height / 2;
  const amplitude = mid - 1.5;

  if (values.length < 2) {
    return (
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        className={className}
        role="img"
        aria-label="Insufficient history for a trace"
      >
        <line
          x1={0}
          y1={mid}
          x2={width}
          y2={mid}
          stroke="currentColor"
          strokeWidth={1}
          strokeDasharray="2 3"
          className="text-ghost"
        />
      </svg>
    );
  }

  const step = width / (values.length - 1);
  const y = (value: number) => mid - Math.max(-1, Math.min(1, value)) * amplitude;
  const points = values.map((value, index) => `${(index * step).toFixed(2)},${y(value).toFixed(2)}`);
  const last = values[values.length - 1] ?? 0;

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      data-state={state}
      className={className}
      role="img"
      aria-label={`Momentum trace over ${values.length} days`}
    >
      <line
        x1={0}
        y1={mid}
        x2={width}
        y2={mid}
        stroke="currentColor"
        strokeWidth={1}
        className="text-edge"
      />
      <polygon
        points={`0,${mid} ${points.join(" ")} ${width},${mid}`}
        className="st-paint"
        opacity={0.14}
      />
      <polyline
        points={points.join(" ")}
        fill="none"
        strokeWidth={1.4}
        strokeLinejoin="round"
        strokeLinecap="round"
        className="st-stroke"
      />
      <circle cx={width} cy={y(last)} r={1.8} className="st-paint" />
    </svg>
  );
}
