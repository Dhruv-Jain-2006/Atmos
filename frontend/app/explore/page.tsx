import Link from "next/link";

export const metadata = { title: "Explore" };

export default function ExplorePage() {
  return (
    <section className="border border-edge bg-panel/50">
      <header className="border-b border-edge px-5 py-2.5">
        <h1 className="font-mono text-[11px] uppercase tracking-[0.28em] text-dim">
          Ecosystem graph
        </h1>
      </header>

      <div className="px-5 py-12 text-center">
        <p className="text-xl leading-tight font-medium tracking-tight text-ink sm:text-2xl">
          The interactive graph is not in this slice.
        </p>
        <p className="mt-3 mx-auto max-w-lg text-[12.5px] leading-relaxed text-faint">
          Explore will render the full technology ecosystem as a navigable graph — zoom,
          pan, search, filter, and inspect relationships between technologies.
        </p>
        <div className="mt-4 inline-flex items-center gap-1.5 rounded border border-edge px-2.5 py-1 font-mono text-[9px] uppercase tracking-[0.14em] text-ghost">
          <span className="size-1 rounded-full bg-ghost" />
          Planned for a later phase
        </div>
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
