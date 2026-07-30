import type { NextConfig } from "next";

const API_BASE = process.env.API_BASE_URL ?? "http://127.0.0.1:8100";

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
    ];
  },
};

export default nextConfig;
