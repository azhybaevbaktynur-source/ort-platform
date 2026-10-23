import type { NextConfig } from "next";

const rawBackend = (process.env.BACKEND_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const BACKEND_URL = rawBackend.endsWith("/api/v1") ? rawBackend.slice(0, -7) : rawBackend;

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${BACKEND_URL}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
