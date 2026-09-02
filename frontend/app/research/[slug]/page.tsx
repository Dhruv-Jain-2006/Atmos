import Link from "next/link";
import { notFound } from "next/navigation";
import type { Metadata } from "next";

import { ConfidenceMeter } from "@/components/instrument/ConfidenceMeter";
import { EpistemicTag } from "@/components/instrument/EpistemicTag";
import { MomentumBar } from "@/components/instrument/MomentumBar";
import { NoObservation } from "@/components/instrument/NoObservation";
import { Panel, Readout } from "@/components/instrument/Panel";
import { StateBadge } from "@/components/instrument/StateBadge";
import { CopilotPanel } from "@/components/research/CopilotPanel";
import { HistoryChart } from "@/components/research/HistoryChart";
import { Provenance } from "@/components/research/Provenance";
import { RelatedTechnologies } from "@/components/research/RelatedTechnologies";
import { SensorTable } from "@/components/research/SensorTable";
import { EventLog } from "@/components/trends/EventLog";
import { SIGNAL_REVALIDATE, VOCABULARY_REVALIDATE, getJson } from "@/lib/api";
import { compact, decimal, isoDate, percent, signed, sigma } from "@/lib/format";
import type {
  EventList,
  TechnologyDetail,
  TechnologyHistory,
  TechnologyRelationships,
  Vocabulary,
} from "@/lib/types";
import { lookup } from "@/lib/vocabulary";

type Params = { slug: string };

const HISTORY_DAYS = 90;

async function load(slug: string) {
  // Four parallel requests, one screen. The detail call decides whether the page
  // exists at all, but firing the others concurrently costs nothing when it does
  // and this page is read far more often than a technology is missing.
  return Promise.all([
    getJson<TechnologyDetail>(`/api/technologies/${slug}`, SIGNAL_REVALIDATE),
    getJson<TechnologyHistory>(
      `/api/technologies/${slug}/history?days=${HISTORY_DAYS}`,
      SIGNAL_REVALIDATE,
    ),
    getJson<TechnologyRelationships>(
      `/api/technologies/${slug}/relationships`,
      SIGNAL_REVALIDATE,
    ),
    getJson<EventList>(`/api/events?technology=${slug}&limit=25`, SIGNAL_REVALIDATE),
    getJson<Vocabulary>("/api/vocabulary", VOCABULARY_REVALIDATE),
  ]);
}

export async function generateMetadata({
  params,
}: {
  params: Promise<Params>;
}): Promise<Metadata> {
  const { slug } = await params;
  const detail = await getJson<TechnologyDetail>(`/api/technologies/${slug}`, SIGNAL_REVALIDATE);
  if (!detail.ok) return { title: slug };
  return {
    title: detail.data.name,
    description: detail.data.summary ?? `Signals, evidence and history for ${detail.data.name}.`,
  };
}

/**
 * Research — the deep investigation experience for one technology.
 *
 * Ordered as CLAUDE.md's loop: the executive question first, then the observed
 * signals, then the history, then the sensors those signals came from, then what
 * is connected to it, then the evidence and its limits, and finally the Copilot.
 *
 * The Copilot and the research engine are out of scope for this slice; both are
 * shown disabled rather than omitted, so the shape of the page is the real one.
 */
export default async function ResearchPage({ params }: { params: Promise<Params> }) {
  const { slug } = await params;
  const [detail, history, relationships, events, vocabulary] = await load(slug);

  // A 404 is a missing technology; anything else is the API being unreachable or
  // degraded, and that must not be rendered as "this technology does not exist".
  if (!detail.ok && detail.status === 404) notFound();

  const vocab = lookup(vocabulary.ok ? vocabulary.data : null);
  const data = detail.ok ? detail.data : null;
  const transportError = detail.ok ? null : detail.error;
  const signals = data?.signals ?? null;
  const emptyReason = transportError ?? data?.freshness.degraded_reason ?? null;
  // Collection fields are optional in the generated contract because they carry
  // server-side defaults. Normalising once here keeps the JSX free of `?? []`.
  const aliases = data?.aliases ?? [];
  const sensors = data?.repositories ?? [];

  if (!data) {
    return (
      <Panel title="Research" caption={slug}>
        <NoObservation
          title="Technology unavailable"
          reason={transportError}
          hint="Start the API with: uv run uvicorn internetweather.api.app:app --reload"
        />
      </Panel>
    );
  }

  const question = data.weather_state
    ? `Why is ${data.name} ${vocab.stateLabel(data.weather_state).toLowerCase()}?`
    : `What is happening with ${data.name}?`;

  return (
    <div className="space-y-4">
      <nav className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.16em] text-ghost">
        <Link href="/" className="transition-colors hover:text-dim">
          Trends
        </Link>
        <span aria-hidden>/</span>
        <span className="text-faint">{vocab.subdomainLabel(data.subdomain)}</span>
        <span aria-hidden>/</span>
        <span className="text-dim">{data.slug}</span>
      </nav>

      {/* ── Executive finding ─────────────────────────────────────────────── */}
      <section
        data-state={data.weather_state ?? undefined}
        className="st-edge border border-edge bg-panel/50"
      >
        <div className="flex flex-wrap items-start justify-between gap-6 px-5 py-5">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-2xl leading-tight font-medium tracking-tight text-ink">
                {data.name}
              </h1>
              {data.weather_state ? (
                <StateBadge state={data.weather_state} vocabulary={vocab} />
              ) : null}
              {data.headline ? (
                <span className="rounded-sm border border-edge-lit px-1.5 py-px font-mono text-[9px] uppercase tracking-[0.14em] text-faint">
                  headline
                </span>
              ) : null}
            </div>

            <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.14em] text-ghost">
              {vocab.subdomainLabel(data.subdomain)} · observed since{" "}
              {isoDate(data.first_seen_at)}
              {aliases.length ? ` · also: ${aliases.join(", ")}` : ""}
            </p>

            {data.summary ? (
              <p className="mt-3 max-w-2xl text-[13px] leading-relaxed text-dim">
                {data.summary}
              </p>
            ) : null}

            <p className="mt-4 text-lg leading-snug text-ink">{question}</p>

            <div className="mt-2 flex flex-wrap items-center gap-2.5">
              <p className="max-w-2xl text-[12px] leading-relaxed text-faint">
                {data.explanation ?? "No explanation computed yet for this technology."}
              </p>
              <EpistemicTag status={data.epistemic_status} />
            </div>

            {/* The engine is not built; the button that would start it is not faked. */}
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <span
                aria-disabled
                title="POST /api/research — contract defined, engine not implemented in this slice"
                className="cursor-not-allowed rounded-sm border border-edge bg-grid/40 px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.16em] text-ghost"
              >
                Investigate
              </span>
              <span className="font-mono text-[9px] uppercase tracking-[0.14em] text-ghost">
                research engine not implemented
              </span>
            </div>
          </div>

          {signals ? (
            <div className="grid shrink-0 grid-cols-2 gap-x-8 gap-y-4">
              <Readout
                label="Momentum"
                emphasis
                hint="Normalised -1..1 composite against this technology's own baseline"
                value={
                  <span className="flex items-baseline gap-2">
                    <span className="st-text">{signed(signals.momentum, 3)}</span>
                    <MomentumBar value={signals.momentum} width={48} />
                  </span>
                }
              />
              <Readout
                label="Confidence"
                emphasis
                hint="How much the observatory trusts this reading"
                value={
                  <span className="flex items-baseline gap-2">
                    {percent(signals.confidence)}
                    <ConfidenceMeter value={signals.confidence} />
                  </span>
                }
              />
              <Readout
                label="Anomaly"
                hint="Standard deviations from this technology's own trailing distribution"
                value={sigma(signals.anomaly_z)}
              />
              <Readout
                label="Observed"
                hint="Distinct days of observation behind this reading"
                value={`${signals.sample_days}d`}
              />
            </div>
          ) : null}
        </div>

        {signals ? (
          <div className="grid grid-cols-2 gap-x-8 gap-y-4 border-t border-edge px-5 py-4 sm:grid-cols-4 lg:grid-cols-7">
            <Readout label="Stars" value={compact(signals.stars_total)} />
            <Readout label="Δ stars 7d" value={signed(signals.stars_delta_7d)} />
            <Readout label="Δ stars 28d" value={signed(signals.stars_delta_28d)} />
            <Readout
              label="Velocity"
              hint="Weighted stars per day over the trailing 7 days"
              value={`${decimal(signals.star_velocity_7d, 1)}/d`}
            />
            <Readout
              label="Acceleration"
              hint="Change in velocity — what 'heating up' actually measures"
              value={signed(signals.star_acceleration, 2)}
            />
            <Readout
              label="Commits"
              hint="Weighted commits per day over the trailing 7 days"
              value={`${decimal(signals.commit_velocity_7d, 1)}/d`}
            />
            <Readout
              label="Sensors"
              hint="Active repositories over total attached repositories"
              value={`${signals.active_repo_count}/${signals.repo_count}`}
            />
          </div>
        ) : (
          <NoObservation
            title="No signal computed"
            reason={emptyReason}
            hint="Signals appear after the first ingestion run followed by the detection worker."
            className="border-t border-edge py-10"
          />
        )}
      </section>

      {/* ── Historical timeline ───────────────────────────────────────────── */}
      <Panel
        title="Timeline"
        caption={`Momentum, velocity and observed state · last ${HISTORY_DAYS} days`}
        right={
          <span className="font-mono text-[10px] tabular-nums text-faint">
            {history.ok ? `${history.data.points.length}d` : "—"}
          </span>
        }
      >
        <HistoryChart
          points={history.ok ? history.data.points : []}
          vocabulary={vocabulary.ok ? vocabulary.data : null}
          emptyReason={history.ok ? emptyReason : history.error}
        />
      </Panel>

      {/* ── Sensors and relationships ─────────────────────────────────────── */}
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="overflow-x-auto min-w-0">
          <Panel
            title="Sensors"
            caption="Repositories observed for this technology"
            right={
              <span className="font-mono text-[10px] tabular-nums text-faint">
                {sensors.length ? String(sensors.length).padStart(2, "0") : "—"}
              </span>
            }
          >
            <SensorTable sensors={sensors} emptyReason={emptyReason} />
          </Panel>
        </div>

        <div className="overflow-x-auto min-w-0">
          <Panel
            title="Related"
            caption="Curated and inferred edges"
            right={
              <span className="font-mono text-[10px] tabular-nums text-faint">
                {relationships.ok && relationships.data.related.length
                  ? String(relationships.data.related.length).padStart(2, "0")
                  : "—"}
              </span>
            }
          >
            <RelatedTechnologies
              related={relationships.ok ? relationships.data.related : []}
              vocabulary={vocabulary.ok ? vocabulary.data : null}
              emptyReason={relationships.ok ? emptyReason : relationships.error}
            />
          </Panel>
        </div>
      </div>

      {/* ── Events ────────────────────────────────────────────────────────── */}
      <EventLog
        events={events.ok ? events.data.items : []}
        vocabulary={vocabulary.ok ? vocabulary.data : null}
        emptyReason={events.ok ? emptyReason : events.error}
      />

      {/* ── Evidence and limits ───────────────────────────────────────────── */}
      <Panel title="Evidence" caption="Derivation, provenance and what remains unknown">
        <Provenance
          signals={signals}
          freshness={data.freshness}
          sensorCount={sensors.length}
        />
      </Panel>

      {/* ── Copilot ───────────────────────────────────────────────────────── */}
      <Panel
        title="Research copilot"
        caption="Contextual to this technology"
        right={
          <span className="font-mono text-[9px] uppercase tracking-[0.14em] text-ghost">
            planned
          </span>
        }
      >
        <CopilotPanel technologyName={data.name} />
      </Panel>

      <p className="font-mono text-[9px] uppercase tracking-[0.14em] text-ghost">
        Signals as of {isoDate(data.freshness.as_of)} · {data.freshness.observed_days} observed
        day(s) · revalidated every {SIGNAL_REVALIDATE}s
      </p>
    </div>
  );
}
