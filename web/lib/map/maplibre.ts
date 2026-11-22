/**
 * MapLibre loader. maplibre-gl 6 is an ES module that starts its tile worker from a URL next to its own file;
 * inside a Next.js chunk that URL does not exist, so the worker is copied to public/maplibre/ at build time
 * (scripts/copy-maplibre-worker.mjs) and set here. Loaded with a dynamic import so it never runs on the server.
 */
let loading: Promise<typeof import("maplibre-gl")> | null = null;

export function loadMaplibre() {
  if (!loading) {
    loading = import("maplibre-gl").then((m) => {
      m.setWorkerUrl(`/maplibre/maplibre-gl-worker.mjs?v=${m.getVersion()}`);
      return m;
    });
  }
  return loading;
}
