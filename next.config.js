/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        // Only forward non-auth API routes to your backend
        source: '/api/backend/:path*',
        destination: 'http://localhost:8010/:path*',
      },
    ]
  },
}
module.exports = nextConfig