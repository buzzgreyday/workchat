import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",

  // `next dev` refuses its dev-only assets and hot-reload socket to any host
  // but the one it started on, so a phone opening this machine by its LAN
  // address gets a page that never hydrates. Set by docker-compose.lan.yaml
  // (via scripts/dev-lan.sh); unset, this is empty and changes nothing.
  // Development only — a production build ignores it.
  allowedDevOrigins: process.env.LAN_IP ? [process.env.LAN_IP] : [],

  async headers() {
    return [
      {
        /**
         * The embed is loaded from other people's pages, which makes it a
         * cross-origin module script — and one without
         * `Access-Control-Allow-Origin` is blocked before it runs. The file
         * downloads, nothing registers, and the host sees an element that
         * never upgrades.
         *
         * `*` rather than an origin list: this is public code, fetched
         * without credentials, and the element is meant to be embeddable.
         * What is guarded is the API, which does keep a list and does take
         * cookies.
         *
         * Set here rather than only in the Caddyfile so it is true of every
         * way this file gets served — `next dev`, the standalone server in
         * the container, and production.
         */
        source: "/embed.js",
        headers: [
          {
            key: "Access-Control-Allow-Origin",
            value: "*",
          },
          {
            // The entry point, and the only thing a host page pins. Cached
            // for a year, a release would reach nobody.
            key: "Cache-Control",
            value: "public, max-age=60, must-revalidate",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
