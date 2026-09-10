import type { NextConfig } from 'next';
import path from 'node:path';

const repositoryRoot = path.resolve(__dirname, '..');
const config: NextConfig = {
  turbopack: { root: repositoryRoot },
  outputFileTracingRoot: repositoryRoot,
};
export default config;
