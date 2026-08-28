import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"

/**
 * React is aliased to preact/compat.
 *
 * The API is identical - same JSX, same hooks, same imports - but the runtime
 * is roughly 40 KB smaller gzipped. On metered mobile data that is most of the
 * download, and this app uses none of the React internals that differ.
 * Remove the alias and it runs on React unchanged.
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      react: "preact/compat",
      "react-dom": "preact/compat",
      "react/jsx-runtime": "preact/jsx-runtime",
    },
  },
  build: {
    // One small bundle beats several round trips on a slow connection.
    cssCodeSplit: false,
    reportCompressedSize: true,
    sourcemap: false,
  },
  server: { port: 5178, host: true },
})
