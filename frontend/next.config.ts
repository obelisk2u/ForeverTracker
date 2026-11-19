import path from "node:path";
import type { NextConfig } from "next";

// Preview the site against another ForeverTracker API, e.g. the live one:
//   API_PROXY=https://forevertracker.org npm run dev
// The server fetches from it directly; the browser calls same-origin /api/* and Next forwards it.
const proxy = process.env.API_PROXY?.replace(/\/$/, "");

const config: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: path.join(__dirname),
  poweredByHeader: false,
  reactStrictMode: true,
  ...(proxy && {
    env: { API_BASE_URL: proxy, NEXT_PUBLIC_API_BASE_URL: "" },
    async rewrites() {
      return [{ source: "/api/:path*", destination: `${proxy}/api/:path*` }];
    },
  }),
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
    ];
  },
};

export default config;
