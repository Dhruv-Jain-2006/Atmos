import type { NextConfig } from "next";

const config: NextConfig = {
  reactStrictMode: true,
  // The frontend talks only to Internet Weather's own API, so there is no
  // external image or asset host to allow.
};

export default config;
