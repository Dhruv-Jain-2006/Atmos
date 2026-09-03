import { ResearchIndex } from "@/components/research/ResearchIndex";
import { SIGNAL_REVALIDATE, VOCABULARY_REVALIDATE, getJson } from "@/lib/api";
import type { TechnologyList, Vocabulary } from "@/lib/types";

export const metadata = { title: "Research" };

/**
 * Research Index — discover and open technology research pages.
 *
 * Fetches the full technology universe in one server request.  The client
 * component handles search, sort and interaction without additional calls.
 */
export default async function ResearchIndexPage() {
  const [technologies, vocabulary] = await Promise.all([
    getJson<TechnologyList>("/api/technologies?limit=200", SIGNAL_REVALIDATE),
    getJson<Vocabulary>("/api/vocabulary", VOCABULARY_REVALIDATE),
  ]);

  const techData = technologies.ok ? technologies.data : null;
  const vocab = vocabulary.ok ? vocabulary.data : null;
  const transportError = technologies.ok ? null : technologies.error;

  return (
    <div className="space-y-4">
      {/* Header */}
      <section className="border border-edge bg-panel/50">
        <header className="border-b border-edge px-5 py-2.5">
          <h1 className="font-mono text-[11px] uppercase tracking-[0.28em] text-dim">
            Technology Research
          </h1>
        </header>
        <div className="px-5 py-4">
          <p className="max-w-2xl text-[13px] leading-relaxed text-faint">
            Investigate the technologies Atmos is currently observing. Each has a
            dedicated research view with executive findings, signal history,
            related technologies, evidence, and an investigation copilot.
          </p>
        </div>
      </section>

      {/* Index */}
      <section className="border border-edge bg-panel/60 backdrop-blur-[1px]">
        {transportError ? (
          <div className="px-5 py-12 text-center">
            <p className="font-mono text-[11px] uppercase tracking-[0.24em] text-dim">
              API unavailable
            </p>
            <p className="mt-2 max-w-md mx-auto font-mono text-[11px] leading-relaxed text-faint">
              {transportError}
            </p>
          </div>
        ) : (
          <ResearchIndex items={techData?.items ?? []} vocabulary={vocab} />
        )}
      </section>
    </div>
  );
}
