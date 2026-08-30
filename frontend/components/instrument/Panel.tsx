import type { ReactNode } from "react";

type ReadoutProps = {
  label: string;
  value: ReactNode;
  hint?: string;
  emphasis?: boolean;
  className?: string;
};

/**
 * A labelled instrument value. Monospace so columns of digits align.
 *
 * Label is 9px uppercase — small enough to not compete with the value.
 * Value is 13px dim (normal) or 18px ink (emphasis) — the dominant element.
 */
export function Readout({ label, value, hint, emphasis, className }: ReadoutProps) {
  return (
    <div className={className} title={hint}>
      <div className="font-mono text-[9px] uppercase tracking-[0.16em] text-faint">{label}</div>
      <div
        className={[
          "font-mono tabular-nums",
          emphasis ? "text-lg leading-snug text-ink" : "text-[13px] leading-tight text-dim",
        ].join(" ")}
      >
        {value}
      </div>
    </div>
  );
}

type PanelProps = {
  title: string;
  caption?: string;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
};

/**
 * A bordered instrument section with a ruled header.
 */
export function Panel({ title, caption, right, children, className }: PanelProps) {
  return (
    <section
      className={[
        "border border-edge bg-panel/60 backdrop-blur-[1px]",
        className ?? "",
      ].join(" ")}
    >
      <header className="flex items-baseline justify-between gap-4 border-b border-edge px-4 py-2.5">
        <div className="flex items-baseline gap-3">
          <h2 className="font-mono text-[11px] uppercase tracking-[0.22em] text-ink">{title}</h2>
          {caption ? (
            <p className="hidden text-[11px] text-faint sm:block">{caption}</p>
          ) : null}
        </div>
        {right}
      </header>
      {children}
    </section>
  );
}
