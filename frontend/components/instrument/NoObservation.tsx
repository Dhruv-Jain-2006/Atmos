type Props = {
  reason?: string | null;
  title?: string;
  hint?: string;
  className?: string;
};

function isDegraded(reason: string | null | undefined): boolean {
  if (!reason) return false;
  const lower = reason.toLowerCase();
  return (
    lower.includes("unreachable") ||
    lower.includes("not configured") ||
    lower.includes("database") ||
    lower.includes("api") ||
    lower.includes("connection")
  );
}

/**
 * The observatory's honest empty state.
 *
 * Distinguishes between three situations:
 * 1. System degraded (API unreachable, no database) — infrastructure issue
 * 2. Awaiting first observation — normal day-one state
 * 3. No signal in this band — the data exists but nothing crossed the threshold
 */
export function NoObservation({
  reason,
  title = "Awaiting first observation",
  hint,
  className,
}: Props) {
  const degraded = isDegraded(reason);

  return (
    <div
      className={[
        "flex flex-col items-center gap-3 px-6 py-14 text-center",
        className ?? "",
      ].join(" ")}
    >
      {degraded ? (
        <span
          aria-hidden
          className="size-2 rounded-full bg-hot/60 shadow-[0_0_12px_var(--color-hot)]"
        />
      ) : (
        <span
          aria-hidden
          className="live-dot size-2 rounded-full bg-signal shadow-[0_0_12px_var(--color-signal)]"
        />
      )}

      <p className="font-mono text-[11px] uppercase tracking-[0.24em] text-dim">{title}</p>

      {reason ? (
        <p className="max-w-md font-mono text-[11px] leading-relaxed text-faint">
          {degraded ? "The observatory is not fully operational." : reason}
        </p>
      ) : null}

      {hint ? (
        <p className="max-w-md text-[11px] leading-relaxed text-ghost">{hint}</p>
      ) : null}
    </div>
  );
}
