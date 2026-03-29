/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_BACKEND_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

/** Injected by vite.config.ts — always resolves to the backend URL (e.g. "http://localhost:8000") */
declare const __BACKEND_URL__: string;
