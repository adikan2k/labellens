import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  cacheComponents: true,
  // Every browser gets the page's title and description in <head>, not streamed in later.
  // Next streams them into <body> for anything but known crawlers, which Lighthouse's SEO
  // check (and link previews that don't run scripts) read as missing.
  htmlLimitedBots: /.*/,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
