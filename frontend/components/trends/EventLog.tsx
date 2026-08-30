import Link from "next/link";

import { EpistemicTag } from "@/components/instrument/EpistemicTag";
import { NoObservation } from "@/components/instrument/NoObservation";
import { Panel } from "@/components/instrument/Panel";
import { isoDate, percent } from "@/lib/format";
import type { EventSummary, Vocabulary } from "@/lib/types";

type Props = {
  events: readonly EventSummary[];
  vocabulary?: Vocabulary | null;
  emptyReason?: string | null;
};

function eventTypeLabel(raw: string): string {
  return raw
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Discrete ecosystem events, as a telemetry log.
 *
 * Trends answers "what is changing"; this answers "what happened". A release, a
 * step change in stars, an archived repository — occurrences with a date, a
 * magnitude and an epistemic standing, ordered newest first.
 */
export function EventLog({ events, emptyReason }: Props) {
  return (
    <Panel
      title="Event log"
      caption="Discrete occurrences, newest first"
      right={
        <span className="font-mono text-[10px] tabular-nums text-faint">
          {events.length ? String(events.length).padStart(2, "0") : "—"}
        </span>
      }
    >
      {events.length === 0 ? (
        <NoObservation
          title="No events recorded"
          reason={emptyReason ?? undefined}
          className="py-10"
        />
      ) : (
        <ol className="divide-y divide-edge/60">
          {events.map((event) => {
            const body = (
              <div className="grid grid-cols-[4.5rem_1fr_auto] items-center gap-x-2.5 px-3 py-2 sm:grid-cols-[5.5rem_6rem_1fr_5rem_auto] sm:gap-x-3 sm:px-4 sm:py-2.5">
                {/* Date */}
                <span className="font-mono text-[10px] tabular-nums text-faint">
                  {isoDate(event.occurred_on)}
                </span>

                {/* Event type — visible on all screens */}
                <span className="hidden font-mono text-[9px] uppercase tracking-[0.12em] text-signal sm:block">
                  {eventTypeLabel(event.event_type)}
                </span>

                {/* Title + technology name */}
                <span className="min-w-0">
                  <span className="block truncate text-[12px] text-ink">{event.title}</span>
                  {event.technology_name ? (
                    <span className="block truncate font-mono text-[9px] uppercase tracking-[0.12em] text-ghost">
                      {event.technology_name}
                    </span>
                  ) : null}
                </span>

                {/* Magnitude — now labelled */}
                <span
                  className="hidden items-center gap-1.5 sm:flex"
                  title={`Significance: ${percent(event.magnitude)}`}
                >
                  <span className="h-1 flex-1 overflow-hidden rounded-full bg-grid">
                    <span
                      className="block h-full bg-signal/70"
                      style={{ width: `${Math.round(event.magnitude * 100)}%` }}
                    />
                  </span>
                  <span className="font-mono text-[9px] tabular-nums text-ghost shrink-0">
                    {percent(event.magnitude)}
                  </span>
                </span>

                {/* Epistemic status */}
                <EpistemicTag status={event.epistemic_status} />
              </div>
            );

            return (
              <li key={event.id}>
                {event.technology_slug ? (
                  <Link
                    href={`/research/${event.technology_slug}`}
                    className="block transition-colors hover:bg-edge/25 focus-visible:bg-edge/25 focus-visible:outline-none"
                  >
                    {body}
                  </Link>
                ) : (
                  body
                )}
              </li>
            );
          })}
        </ol>
      )}
    </Panel>
  );
}
