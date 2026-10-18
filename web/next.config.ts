import type { NextConfig } from "next";

const API_BASE = process.env.API_BASE_URL ?? "http://127.0.0.1:8100";

// Datasette, a read-only table browser over the same SQLite file. Owner only:
// src/proxy.ts refuses /db to anyone else before this rewrite is reached.
const DB_BASE = process.env.DB_BASE_URL ?? "http://127.0.0.1:8200";

const nextConfig: NextConfig = {
  // Proxy the API so the browser only ever talks to this origin. One tunnelled
  // port instead of two, and no CORS in the request path:
  //   ssh -L 3100:localhost:3100 oci
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${API_BASE}/api/:path*`,
      },
      { source: "/db", destination: `${DB_BASE}/db/` },
      { source: "/db/:path*", destination: `${DB_BASE}/db/:path*` },
    ];
  },
};

export default nextConfig;
