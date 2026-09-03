import { NoObservation } from "@/components/instrument/NoObservation";
import { compact, decimal, isoDate, signed } from "@/lib/format";
import type { HistoryPoint, Vocabulary } from "@/lib/types";
import { lookup } from "@/lib/vocabulary";

type Props = {
  points: readonly HistoryPoint[];
  vocabulary: Vocabulary | null;
  emptyReason?: string | null;
};

// One fixed viewBox, scaled by CSS. Strokes carry `vector-effect` so hairlines
// stay hairlines at any width instead of thickening with the scale factor.
const W = 900;
const H = 268;
const PAD_L = 46;
const PAD_R = 14;
const PLOT_TOP = 16;
const PLOT_H = 150;
const VEL_TOP = 184;
const VEL_H = 40;
const RIBBON_TOP = 234;
const RIBBON_H = 9;
const AXIS_Y = 260;

const MOMENTUM_TICKS = [1, 0.5, 0, -0.5, -1] as const;

/**
 * Historical timeline: momentum, star velocity and observed weather state on one
 * shared time axis.
 *
 * Three tracks rather than three charts, because the question is temporal
 * correlation — did the state change when velocity did? — and that is unanswerable
 * across separately-scaled panels.
 *
 * Momentum uses a fixed -1..1 domain (it is already normalised), so the same
 * slope means the same thing on every technology's page. Velocity is scaled to
 * its own maximum and labelled with it, since stars/day has no natural ceiling.
 *
 * Rendered on the server: no charting library, no client bundle, and tooltips
 * come from native SVG `<title>` on per-day hit strips.
 */
export function HistoryChart({ points, vocabulary, emptyReason }: Props) {
  const vocab = lookup(vocabulary);

  if (points.length === 0) {
    return (
      <NoObservation
        title="No history recorded"
        reason={emptyReason ?? undefined}
        hint="A timeline needs repeated observation. It fills in one day per ingestion run."
        className="py-12"
      />
    );
  }

  const plotW = W - PAD_L - PAD_R;
  const span = Math.max(points.length - 1, 1);
  const x = (index: number) =>
    points.length === 1 ? PAD_L + plotW / 2 : PAD_L + (index / span) * plotW;
  const yMomentum = (value: number) => {
    const clamped = Math.max(-1, Math.min(1, value));
    return PLOT_TOP + ((1 - clamped) / 2) * PLOT_H;
  };

  const velocities = points.map((p) => p.star_velocity_7d ?? 0);
  const velMax = Math.max(...velocities.map(Math.abs), 1);
  const bandW = Math.max(plotW / points.length, 1);

  const line = points.map((p, i) => `${x(i).toFixed(2)},${yMomentum(p.momentum).toFixed(2)}`);
  const zeroY = yMomentum(0);
  const area = `${PAD_L},${zeroY} ${line.join(" ")} ${x(points.length - 1)},${zeroY}`;

  // Roughly six date labels regardless of window length.
  const labelEvery = Math.max(1, Math.ceil(points.length / 6));
  const last = points[points.length - 1];

  return (
    <figure className="px-4 py-4">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="h-auto w-full"
        role="img"
        aria-label={`Momentum, star velocity and weather state across ${points.length} observed days`}
      >
        {/* Momentum gridlines and scale */}
        {MOMENTUM_TICKS.map((tick) => (
          <g key={tick}>
            <line
              x1={PAD_L}
              x2={W - PAD_R}
              y1={yMomentum(tick)}
              y2={yMomentum(tick)}
              stroke={tick === 0 ? "var(--color-edge-lit)" : "var(--color-grid)"}
              strokeDasharray={tick === 0 ? undefined : "2 5"}
              vectorEffect="non-scaling-stroke"
            />
            <text
              x={PAD_L - 8}
              y={yMomentum(tick) + 3.5}
              textAnchor="end"
              className="fill-ghost font-mono"
              fontSize="9"
            >
              {tick > 0 ? `+${tick}` : tick}
            </text>
          </g>
        ))}

        {/* Momentum trace */}
        <polygon points={area} fill="var(--color-signal)" opacity="0.1" />
        <polyline
          points={line.join(" ")}
          fill="none"
          stroke="var(--color-signal)"
          strokeWidth="1.5"
          strokeLinejoin="round"
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />
        {points.length === 1 ? (
          <circle cx={x(0)} cy={yMomentum(points[0]!.momentum)} r="2.5" fill="var(--color-signal)" />
        ) : null}

        {/* Star velocity, own scale, stated in the axis label */}
        <line
          x1={PAD_L}
          x2={W - PAD_R}
          y1={VEL_TOP + VEL_H}
          y2={VEL_TOP + VEL_H}
          stroke="var(--color-edge)"
          vectorEffect="non-scaling-stroke"
        />
        {points.map((point, i) => {
          const value = point.star_velocity_7d ?? 0;
          const height = (Math.abs(value) / velMax) * VEL_H;
          return (
            <rect
              key={`v-${point.day}`}
              x={x(i) - bandW * 0.34}
              y={VEL_TOP + VEL_H - height}
              width={bandW * 0.68}
              height={height}
              fill="var(--color-dim)"
              opacity={value === 0 ? 0.18 : 0.55}
            />
          );
        })}
        <text
          x={PAD_L - 8}
          y={VEL_TOP + 8}
          textAnchor="end"
          className="fill-ghost font-mono"
          fontSize="9"
        >
          {decimal(velMax, 1)}
        </text>
        <text
          x={PAD_L - 8}
          y={VEL_TOP + VEL_H}
          textAnchor="end"
          className="fill-ghost font-mono"
          fontSize="9"
        >
          0
        </text>

        {/* Observed weather state, one cell per day */}
        {points.map((point, i) => (
          <rect
            key={`s-${point.day}`}
            data-state={point.weather_state}
            className="st-paint"
            x={x(i) - bandW / 2}
            y={RIBBON_TOP}
            width={bandW}
            height={RIBBON_H}
            opacity="0.85"
          />
        ))}

        {/* Date axis */}
        {points.map((point, i) =>
          i % labelEvery === 0 || i === points.length - 1 ? (
            <text
              key={`d-${point.day}`}
              x={x(i)}
              y={AXIS_Y}
              textAnchor={i === 0 ? "start" : i === points.length - 1 ? "end" : "middle"}
              className="fill-ghost font-mono"
              fontSize="9"
            >
              {isoDate(point.day).slice(5)}
            </text>
          ) : null,
        )}

        {/* Native tooltips. Full-height hit strips, so the whole column is a target. */}
        {points.map((point, i) => (
          <rect
            key={`h-${point.day}`}
            x={x(i) - bandW / 2}
            y={PLOT_TOP}
            width={bandW}
            height={RIBBON_TOP + RIBBON_H - PLOT_TOP}
            fill="transparent"
          >
            <title>
              {`${isoDate(point.day)} · ${vocab.stateLabel(point.weather_state)}`
                + `\nmomentum ${signed(point.momentum, 3)}`
                + `\nvelocity ${decimal(point.star_velocity_7d, 1)} stars/day`
                + `\nstars ${compact(point.stars_total)}`
                + `\nconfidence ${Math.round(point.confidence * 100)}%`}
            </title>
          </rect>
        ))}
      </svg>

      <figcaption className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1.5 border-t border-edge/60 pt-3 font-mono text-[9px] uppercase tracking-[0.14em] text-ghost">
        <span className="flex items-center gap-1.5">
          <span aria-hidden className="h-px w-4 bg-signal" />
          momentum (−1…+1)
        </span>
        <span className="flex items-center gap-1.5">
          <span aria-hidden className="h-2 w-1.5 bg-dim/60" />
          star velocity /day
        </span>
        <span className="flex items-center gap-1.5">
          <span aria-hidden className="h-2 w-4 rounded-[1px] bg-edge-lit" />
          observed state
        </span>
        <span className="ml-auto text-faint">
          {points.length}d · latest {isoDate(last?.day)}
        </span>
      </figcaption>
    </figure>
  );
}
