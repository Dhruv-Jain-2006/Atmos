"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/", label: "Trends", match: "/" },
  { href: "/explore", label: "Explore", match: "/explore" },
  { href: "/research", label: "Research", match: "/research" },
] as const;

const BASE =
  "rounded-sm px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.16em] transition-colors";

export function NavLinks() {
  const pathname = usePathname();

  return (
    <nav className="flex items-center gap-0.5 sm:gap-1" aria-label="Primary">
      {links.map(({ href, label, match }) => {
        const active = match === "/" ? pathname === "/" : pathname.startsWith(match);
        return (
          <Link
            key={href}
            href={href}
            className={
              active
                ? `${BASE} border border-edge-lit bg-edge/40 text-ink`
                : `${BASE} border border-transparent text-dim hover:bg-edge/40 hover:text-ink`
            }
            aria-current={active ? "page" : undefined}
          >
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
