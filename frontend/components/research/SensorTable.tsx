import { NoObservation } from "@/components/instrument/NoObservation";
import { compact, daysAgo, decimal } from "@/lib/format";
import type { RepositorySensor } from "@/lib/types";

type Props = {
  sensors: readonly RepositorySensor[];
  emptyReason?: string | null;
};

const RELATION_HINT: Record<string, string> = {
  canonical: "The reference implementation. Highest weight in the aggregate.",
  implementation: "An independent implementation of the same technology.",
  integration: "Integrates the technology as a dependency or adapter.",
  ecosystem: "Adjacent tooling. Lowest weight; counted but does not lead.",
};

/**
 * The repositories observed on behalf of this technology.
 *
 * CLAUDE.md's framing: GitHub is a developer-behaviour sensor. This table is the
 * sensor list — the physical basis of every number on the page. Weight is shown
 * because a technology's signal is a weighted aggregate, and a reader who cannot
 * see the weights cannot audit the conclusion.
 *
 * Archived repositories stay listed and are marked. Removing them would quietly
 * change the denominator of the aggregate.
 */
export function SensorTable({ sensors, emptyReason }: Props) {
  if (sensors.length === 0) {
    return (
      <NoObservation
        title="No sensors attached"
        reason={emptyReason ?? undefined}
        hint="Repositories are attached by the resolve worker, which maps owner/name to an immutable GitHub id."
        className="py-12"
      />
    );
  }

  const totalWeight = sensors.reduce((sum, sensor) => sum + sensor.weight, 0);

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[620px] border-collapse text-left">
        <thead>
          <tr className="border-b border-edge">
            {["Repository", "Relation", "Weight", "Stars", "Forks", "Language", "Last push"].map(
              (heading, index) => (
                <th
                  key={heading}
                  scope="col"
                  className={[
                    "px-4 py-2 font-mono text-[9px] font-normal uppercase tracking-[0.14em] text-ghost",
                    index >= 2 && index <= 4 ? "text-right" : "",
                  ].join(" ")}
                >
                  {heading}
                </th>
              ),
            )}
          </tr>
        </thead>
        <tbody className="divide-y divide-edge/60">
          {sensors.map((sensor) => (
            <tr key={sensor.full_name} className="transition-colors hover:bg-edge/20">
              <td className="px-4 py-2.5">
                <a
                  href={sensor.url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="font-mono text-[11px] text-ink underline decoration-edge-lit decoration-dotted underline-offset-2 hover:decoration-signal"
                >
                  {sensor.full_name}
                </a>
                {sensor.is_archived ? (
                  <span className="ml-2 rounded-sm border border-cooling/40 px-1 py-px font-mono text-[8px] uppercase tracking-[0.12em] text-cooling">
                    archived
                  </span>
                ) : null}
              </td>
              <td
                className="px-4 py-2.5 font-mono text-[10px] uppercase tracking-[0.1em] text-faint"
                title={RELATION_HINT[sensor.relation]}
              >
                {sensor.relation}
              </td>
              <td className="px-4 py-2.5 text-right">
                <span className="flex items-center justify-end gap-2">
                  <span className="font-mono text-[11px] tabular-nums text-dim">
                    {decimal(sensor.weight, 2)}
                  </span>
                  <span aria-hidden className="h-1 w-8 overflow-hidden rounded-full bg-grid">
                    <span
                      className="block h-full bg-signal/70"
                      style={{
                        width: `${totalWeight > 0 ? (sensor.weight / totalWeight) * 100 : 0}%`,
                      }}
                    />
                  </span>
                </span>
              </td>
              <td className="px-4 py-2.5 text-right font-mono text-[11px] tabular-nums text-dim">
                {compact(sensor.stars)}
              </td>
              <td className="px-4 py-2.5 text-right font-mono text-[11px] tabular-nums text-faint">
                {compact(sensor.forks)}
              </td>
              <td className="px-4 py-2.5 font-mono text-[10px] text-faint">
                {sensor.primary_language ?? "—"}
              </td>
              <td className="px-4 py-2.5 font-mono text-[10px] tabular-nums text-faint">
                {daysAgo(sensor.pushed_at)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
