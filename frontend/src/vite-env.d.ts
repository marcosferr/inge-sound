/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base path of the API. Defaults to the same-origin `/api`. */
  readonly VITE_API_BASE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
