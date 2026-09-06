import Link from "next/link";

import { NavLinks } from "@/components/shell/NavLinks";
import { getJson } from "@/lib/api";
import type { Health } from "@/lib/types";

type Condition = {
  label: string;
  detail: string;
  dotClass: string;
  textClass: string;
  live: boolean;
};

async function condition(): Promise<Condition> {
  const result = await getJson<Health>("/health", 30);
  if (!result.ok) {
    return {
      label: "offline",
      detail: result.error,
      dotClass: "bg-storm",
      textClass: "text-storm",
      live: false,
    };
  }
  if (result.data.status === "ok") {
    return {
      label: "observing",
      detail: `${result.data.environment} · v${result.data.version}`,
      dotClass: "bg-emerging",
      textClass: "text-emerging",
      live: true,
    };
  }
  return {
    label: "degraded",
    detail: result.data.database.error ?? "no database configured",
    dotClass: "bg-hot",
    textClass: "text-hot",
    live: false,
  };
}

/**
 * Site chrome, and a live statement of whether the observatory is actually
 * looking. A platform that claims continuous observation should not require a
 * separate status page to tell you it stopped.
 */
export async function SiteHeader() {
  const status = await condition();

  return (
    <header className="sticky top-0 z-40 border-b border-edge bg-void/85 backdrop-blur-md">
      <div className="mx-auto flex max-w-[1400px] flex-wrap items-center justify-between gap-x-6 gap-y-2.5 px-4 py-2.5 sm:gap-x-8 sm:px-5 sm:py-3">
        <Link href="/" className="group flex items-baseline gap-2.5 sm:gap-3">
          <span className="text-[12px] font-semibold tracking-[0.2em] text-ink uppercase sm:text-[13px]">
            Atmos
          </span>
          <span className="hidden font-mono text-[9px] uppercase tracking-[0.2em] text-ghost sm:inline">
            AI engineering observatory
          </span>
        </Link>

        <NavLinks />

        <div className="flex items-center gap-3" title={status.detail}>
          <Link
            href="https://github.com/Dhruv-Jain-2006/Atmos"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 rounded-sm border border-edge-lit bg-edge/40 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.16em] text-ghost transition-colors hover:bg-edge/70 hover:text-ink"
            title="View on GitHub"
          >
            <svg viewBox="0 0 16 16" className="size-3 fill-current">
              <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
            </svg>
            GitHub
          </Link>
          <span
            aria-hidden
            className={`${status.dotClass} ${status.live ? "live-dot" : ""} size-1.5 rounded-full`}
          />
          <span className={`${status.textClass} font-mono text-[10px] uppercase tracking-[0.18em]`}>
            {status.label}
          </span>
        </div>
      </div>
    </header>
  );
}
