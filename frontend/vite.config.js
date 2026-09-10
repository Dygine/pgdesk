import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

import { readFileSync } from 'node:fs'

// The running bundle has to know its own version to compare against the
// manifest. Read from package.json at build time so one edit - `npm version` -
// stamps the bundle, the manifest and the Android versionName together, rather
// than three numbers drifting apart.
const pkgVersion = JSON.parse(readFileSync('./package.json', 'utf8')).version

export default defineConfig({
  define: {
    'import.meta.env.VITE_APP_VERSION': JSON.stringify(pkgVersion),
  },
  plugins: [react()],
  resolve: { alias: { '@': path.resolve(__dirname, './src') } },
  server: { port: 5173, host: true },
})
