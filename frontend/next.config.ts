import type { NextConfig } from 'next';
import path from 'node:path';

const repositoryRoot = path.resolve(__dirname, '..');
const config: NextConfig = {
  async headers(){return [{source:'/:path*',headers:[{key:'X-Content-Type-Options',value:'nosniff'},{key:'X-Frame-Options',value:'DENY'},{key:'Referrer-Policy',value:'no-referrer'},{key:'Permissions-Policy',value:'camera=(), microphone=(), geolocation=()'}]},{source:'/sw.js',headers:[{key:'Cache-Control',value:'no-cache'}]},{source:'/patient/:path*',headers:[{key:'Cache-Control',value:'no-store'},{key:'X-Robots-Tag',value:'noindex, nofollow'}]},{source:'/self-checkin/:path*',headers:[{key:'Cache-Control',value:'no-store'},{key:'X-Robots-Tag',value:'noindex, nofollow'}]}];},
  turbopack: { root: repositoryRoot },
  outputFileTracingRoot: repositoryRoot,
};
export default config;
