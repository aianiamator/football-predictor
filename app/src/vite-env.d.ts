/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the published JSON. Set at build time to the Cloudflare origin. */
  readonly VITE_DATA_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
