/**
 * Number and date formatting for instrument readouts.
 *
 * One rule throughout: a value that was never measured renders as an em dash,
 * never as zero. "0 stars/day" and "we did not observe this" are different
 * claims, and conflating them is how a dashboard starts lying quietly.
 */

export const NO_VALUE = "—";

export function compact(value: number | null | undefined): string {
  if (value === null || value === undefined) return NO_VALUE;
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `${(value / 1_000_000).toFixed(abs >= 10_000_000 ? 0 : 1)}M`;
  if (abs >= 1_000) return `${(value / 1_000).toFixed(abs >= 10_000 ? 0 : 1)}k`;
  return Math.round(value).toString();
}

export function signed(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined) return NO_VALUE;
  const formatted = digits > 0 ? Math.abs(value).toFixed(digits) : compact(Math.abs(value));
  if (value > 0) return `+${formatted}`;
  if (value < 0) return `-${formatted}`;
  return formatted;
}

export function decimal(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined) return NO_VALUE;
  return value.toFixed(digits);
}

export function sigma(value: number | null | undefined): string {
  if (value === null || value === undefined) return NO_VALUE;
  return `${value >= 0 ? "+" : "−"}${Math.abs(value).toFixed(1)}σ`;
}

export function percent(value: number | null | undefined): string {
  if (value === null || value === undefined) return NO_VALUE;
  return `${Math.round(value * 100)}%`;
}

/** ISO date (YYYY-MM-DD) rendered as a stable, locale-free instrument label. */
export function isoDate(value: string | null | undefined): string {
  if (!value) return NO_VALUE;
  return value.slice(0, 10);
}

/** UTC timestamp readout. Fixed to UTC so server and client agree. */
export function timestamp(value: string | null | undefined): string {
  if (!value) return NO_VALUE;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return NO_VALUE;
  const iso = parsed.toISOString();
  return `${iso.slice(0, 10)} ${iso.slice(11, 16)}Z`;
}

export function daysAgo(value: string | null | undefined, today = new Date()): string {
  if (!value) return NO_VALUE;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return NO_VALUE;
  const days = Math.floor((today.getTime() - parsed.getTime()) / 86_400_000);
  if (days <= 0) return "today";
  if (days === 1) return "1d ago";
  return `${days}d ago`;
}
