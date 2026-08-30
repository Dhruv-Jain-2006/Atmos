import { ClimateStrip } from "@/components/trends/ClimateStrip";
import { EventLog } from "@/components/trends/EventLog";
import { SignalBand } from "@/components/trends/SignalBand";
import { StationHeader } from "@/components/trends/StationHeader";
import { SIGNAL_REVALIDATE, VOCABULARY_REVALIDATE, getJson } from "@/lib/api";
import type { Trends, Vocabulary } from "@/lib/types";

/**
 * Trends — the primary discovery page.
 *
 * One request paints the whole screen. `/api/trends` returns global conditions,
 * the four ranked bands and the event log together, because assembling one view
 * from four round trips is what makes an interface feel like a dashboard rather
 * than an instrument.
 *
 * The vocabulary (glyphs, labels, state meanings) comes from the API too, so the
 * UI never hardcodes a semantic the classifier owns. It is cached for a day; the
 * signals for a minute.
 */
export default async function TrendsPage() {
  const [trends, vocabulary] = await Promise.all([
    getJson<Trends>("/api/trends", SIGNAL_REVALIDATE),
    getJson<Vocabulary>("/api/vocabulary", VOCABULARY_REVALIDATE),
  ]);

  const data = trends.ok ? trends.data : null;
  const vocab = vocabulary.ok ? vocabulary.data : null;
  const transportError = trends.ok ? null : trends.error;

  const emptyReason =
    transportError ?? data?.freshness.degraded_reason ?? "No signal above threshold yet.";

  return (
    <div className="space-y-4">
      <StationHeader
        overview={data?.overview ?? null}
        freshness={data?.freshness ?? null}
        vocabulary={vocab}
        transportError={transportError}
      />

      <ClimateStrip climates={data?.overview.subdomains ?? []} vocabulary={vocab} />

      <div className="grid gap-4 lg:grid-cols-2">
        <SignalBand
          title="Heating"
          caption="Fastest positive momentum — accelerating against their own 28-day baseline"
          items={data?.heating ?? []}
          vocabulary={vocab}
          emptyReason={emptyReason}
        />
        <SignalBand
          title="Cooling"
          caption="Fastest negative momentum — decelerating against their own 28-day baseline"
          items={data?.cooling ?? []}
          vocabulary={vocab}
          emptyReason={emptyReason}
        />
        <SignalBand
          title="Emerging"
          caption="Small-base acceleration — low absolute scale, high slope"
          items={data?.emerging ?? []}
          vocabulary={vocab}
          emptyReason={emptyReason}
        />
        <SignalBand
          title="Anomalies"
          caption="Statistically unusual versus their own history, either direction"
          items={data?.anomalies ?? []}
          vocabulary={vocab}
          emptyReason={emptyReason}
        />
      </div>

      <EventLog events={data?.events ?? []} vocabulary={vocab} emptyReason={emptyReason} />
    </div>
  );
}
