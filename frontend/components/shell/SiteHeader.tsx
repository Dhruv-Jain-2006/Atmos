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

        <div className="flex items-center gap-2" title={status.detail}>
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
