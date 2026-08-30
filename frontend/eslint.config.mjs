import next from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

/**
 * Flat config. `lib/types.gen.ts` is ignored because it is generated from
 * `docs/openapi.json` — lint findings there are findings about the generator,
 * and the file must never be hand-edited to satisfy them.
 */
const config = [
  {
    ignores: [".next/**", "node_modules/**", "next-env.d.ts", "lib/types.gen.ts"],
  },
  ...next,
  ...nextTypescript,
];

export default config;
