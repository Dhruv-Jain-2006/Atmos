/**
 * The frontend's only door to data.
 *
 * Two rules from CLAUDE.md are enforced here rather than trusted:
 *
 * 1. The frontend never calls an external API. Everything goes through Internet
 *    Weather's own normalized surface, so this module has exactly one base URL.
 * 2. A missing or unreachable backend is a state to render, not an exception to
 *    throw. `getJson` never rejects — it returns a discriminated result, and the
 *    caller renders the observatory's "no observation" state. That is also what
 *    lets `next build` succeed with no API running.
 */

const DEFAULT_BASE = "http://127.0.0.1:8000";

/** Server components read API_BASE_URL; the public var exists for client use. */
const BASE = (
  process.env.API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  DEFAULT_BASE
).replace(/\/+$/, "");

/**
 * Signals are recomputed a few times a day, so a 60s window is generous and
 * keeps a page refresh from becoming a database wake-up on Neon's free tier.
 */
export const SIGNAL_REVALIDATE = 60;

/** The semantic vocabulary is static; it changes only when the code does. */
export const VOCABULARY_REVALIDATE = 86_400;

export type ApiResult<T> =
  | { ok: true; data: T }
  | { ok: false; status: number | null; error: string };

export async function getJson<T>(
  path: string,
  revalidate: number = SIGNAL_REVALIDATE,
): Promise<ApiResult<T>> {
  const url = `${BASE}${path}`;
  try {
    const response = await fetch(url, {
      headers: { accept: "application/json" },
      next: { revalidate },
    });
    if (!response.ok) {
      return {
        ok: false,
        status: response.status,
        error: `API responded ${response.status} for ${path}`,
      };
    }
    return { ok: true, data: (await response.json()) as T };
  } catch {
    // Connection refused, DNS failure, timeout. The API is not there.
    return { ok: false, status: null, error: `API unreachable at ${BASE}` };
  }
}

export const apiBaseUrl = BASE;
