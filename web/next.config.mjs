/** @type {import('next').NextConfig} */
const nextConfig = {
  // The typed API client in web/lib/api.ts is the only bridge to FastAPI
  // (ADR-003). Caddy routes /api to the api service in the Compose stack, so
  // the browser calls /api/* on the same origin; no rewrites are needed here.
  reactStrictMode: true,
};

export default nextConfig;
