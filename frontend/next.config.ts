import type { NextConfig } from 'next';
import path from 'node:path';

const repositoryRoot = path.resolve(__dirname, '..');
const privatePageHeaders = [
  { key: 'Cache-Control', value: 'no-store' },
  { key: 'X-Robots-Tag', value: 'noindex, nofollow' },
];

const config: NextConfig = {
  poweredByHeader: false,
  images: { unoptimized: true },
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'Referrer-Policy', value: 'no-referrer' },
          { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=()' },
          {
            key: 'Content-Security-Policy',
            value: "base-uri 'none'; frame-ancestors 'none'; form-action 'self'; object-src 'none'",
          },
        ],
      },
      {
        source: '/api/:path*',
        headers: [{
          key: 'Content-Security-Policy',
          value: "default-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
        }],
      },
      { source: '/sw.js', headers: [{ key: 'Cache-Control', value: 'no-cache' }] },
      { source: '/patient/:path*', headers: privatePageHeaders },
      { source: '/self-checkin/:path*', headers: privatePageHeaders },
    ];
  },
  turbopack: { root: repositoryRoot },
  outputFileTracingRoot: repositoryRoot,
};
export default config;
