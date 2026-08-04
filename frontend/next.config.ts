import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Leaflet owns an imperative map container and is not compatible with React's dev-only double mount.
  reactStrictMode: false,
};

export default nextConfig;
