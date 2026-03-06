import type { NextConfig } from "next"

const isProductionBuild = process.env.NODE_ENV === "production"

const nextConfig: NextConfig = {
  reactCompiler: true,
  output: "export",
  trailingSlash: true,
  assetPrefix: isProductionBuild ? "/_fastapi-domain-monitor-static" : undefined,
  images: {
    unoptimized: true,
  },
}

export default nextConfig
