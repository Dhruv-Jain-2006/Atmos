"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

const links = [
  { href: "/", label: "Trends", match: "/" },
  { href: "/explore", label: "Explore", match: "/explore" },
  { href: "/research", label: "Research", match: "/research" },
] as const;

export function NavLinks() {
  const pathname = usePathname();
  const containerRef = useRef<HTMLDivElement>(null);
  const linkRefs = useRef<(HTMLAnchorElement | null)[]>([]);
  const [indicator, setIndicator] = useState<{ left: number; width: number }>({
    left: 0,
    width: 0,
  });

  const activeIndex = links.findIndex(({ match }) =>
    match === "/" ? pathname === "/" : pathname.startsWith(match),
  );

  useEffect(() => {
    const el = linkRefs.current[activeIndex];
    const container = containerRef.current;
    if (!el || !container) return;

    const containerRect = container.getBoundingClientRect();
    const linkRect = el.getBoundingClientRect();

    setIndicator({
      left: linkRect.left - containerRect.left,
      width: linkRect.width,
    });
  }, [activeIndex]);

  return (
    <nav
      ref={containerRef}
      className="relative flex items-center gap-0.5 sm:gap-1"
      aria-label="Primary"
    >
      {/* Sliding glass highlight */}
      <div
        className="nav-glass-pill"
        style={{
          transform: `translateX(${indicator.left}px)`,
          width: indicator.width,
        }}
        aria-hidden
      />

      {links.map(({ href, label, match }, i) => {
        const active = match === "/" ? pathname === "/" : pathname.startsWith(match);
        return (
          <Link
            key={href}
            ref={(el) => { linkRefs.current[i] = el; }}
            href={href}
            className={`relative z-10 rounded-sm px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.16em] transition-colors duration-200 ${
              active ? "text-ink" : "text-dim hover:text-ink"
            }`}
            aria-current={active ? "page" : undefined}
          >
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
