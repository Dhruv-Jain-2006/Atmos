/**
 * Presentation-side vocabulary helpers.
 *
 * Glyphs, labels and meanings are NOT defined here. They come from
 * `GET /api/vocabulary`, so the classifier and the UI cannot drift apart. When
 * the API is unreachable the lookup falls back to the raw key rather than
 * inventing a glyph — an unlabelled reading is honest; a wrong one is not.
 *
 * What does live here is purely visual: display order, and the colour token each
 * state maps to. Colour is a rendering decision, not a semantic claim.
 */

import type { Subdomain, Vocabulary, WeatherState } from "./types";

/** Most urgent first. Drives legend order, not ranking. */
export const STATE_ORDER: readonly WeatherState[] = [
  "breaking",
  "storm",
  "hot",
  "emerging",
  "stable",
  "cooling",
] as const;

export type VocabularyLookup = {
  stateLabel: (state: WeatherState) => string;
  stateGlyph: (state: WeatherState) => string;
  stateMeaning: (state: WeatherState) => string;
  subdomainLabel: (key: Subdomain) => string;
  /** True when labels came from the API rather than the fallback. */
  resolved: boolean;
};

/** Last-resort label: the key itself, made readable. Never a glyph. */
function humanise(key: string): string {
  return key.replace(/_/g, " ").toUpperCase();
}

export function lookup(vocabulary: Vocabulary | null): VocabularyLookup {
  const states = new Map(
    (vocabulary?.weather_states ?? []).map((entry) => [entry.state, entry]),
  );
  const subdomains = new Map(
    (vocabulary?.subdomains ?? []).map((entry) => [entry.key, entry.label]),
  );

  return {
    resolved: states.size > 0,
    stateLabel: (state) => states.get(state)?.label ?? humanise(state),
    stateGlyph: (state) => states.get(state)?.glyph ?? "",
    stateMeaning: (state) => states.get(state)?.meaning ?? "",
    subdomainLabel: (key) => subdomains.get(key) ?? humanise(key),
  };
}
