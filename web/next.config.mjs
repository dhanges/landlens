/** @type {import('next').NextConfig} */
// The typed API client in web/lib/api.ts is the only bridge to FastAPI (ADR-003). In the Compose stack Caddy
// routes /api and /tiles on the same origin, so no rewrites are needed. For `npm run dev` outside Compose, set
// LANDLENS_DEV_PROXY=http://localhost (Caddy) and the dev server forwards /api and /tiles there.
const proxy = process.env.LANDLENS_DEV_PROXY;

const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  async rewrites() {
    if (!proxy) return [];
    return [
      { source: "/api/:path*", destination: `${proxy}/api/:path*` },
      { source: "/tiles/:path*", destination: `${proxy}/tiles/:path*` },
    ];
  },
};

export default nextConfig;
