import Link from "next/link";

export const metadata = { title: "No such station" };

/**
 * 404 in the observatory's own idiom. A missing technology is a real answer —
 * "we are not observing this" — not a system error, and it should read that way.
 */
export default function NotFound() {
  return (
    <section className="border border-edge bg-panel/50">
      <header className="border-b border-edge px-5 py-2.5">
        <h1 className="font-mono text-[11px] uppercase tracking-[0.28em] text-dim">
          Not observed
        </h1>
      </header>

      <div className="px-5 py-12 text-center">
        <p className="text-xl leading-tight font-medium tracking-tight text-ink sm:text-2xl">
          Nothing is being tracked at this address.
        </p>
        <p className="mt-3 mx-auto max-w-lg text-[12.5px] leading-relaxed text-faint">
          The technology universe is curated: roughly forty technologies across seven AI
          engineering subdomains. If something is missing, it has not been added to
          <span className="font-mono text-[11.5px] text-dim"> technology_universe.yml</span> yet
          — which is a gap in coverage, not a failure.
        </p>
        <div className="mt-6">
          <Link
            href="/"
            className="inline-flex items-center gap-2 rounded-sm border border-edge-lit bg-edge/40 px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.16em] text-ink transition-colors hover:bg-edge/70"
          >
            ← Back to trends
          </Link>
        </div>
      </div>
    </section>
  );
}
