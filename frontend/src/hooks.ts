import { useState, useEffect, useCallback, useMemo } from "react";
import type { Dashboard, BacklogItem, CallIndex, CallDetail, CustDev } from "./types";
import { useOverrides, applyThresholds } from "./thresholds";

const BASE = import.meta.env.BASE_URL || "/";

export function useDashboard() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${BASE}data/dashboard.json`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return { data, loading, error };
}

/** Dashboard with all metrics re-banded by the user's active thresholds.
 *  Use this on every page that renders metric bands/verdicts. */
export function useDashboardTuned() {
  const { data, loading, error } = useDashboard();
  const overrides = useOverrides();
  const tuned = useMemo(
    () => (data ? applyThresholds(data, overrides) : null),
    [data, overrides]
  );
  return { data: tuned, loading, error };
}

export function useBacklog() {
  const [data, setData] = useState<BacklogItem[]>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    fetch(`${BASE}data/backlog.json`)
      .then((r) => r.json())
      .then(setData)
      .catch(() => setData([]))
      .finally(() => setLoading(false));
  }, []);
  return { data, loading };
}

export function useCallIndex() {
  const [data, setData] = useState<CallIndex[]>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    fetch(`${BASE}data/calls/index.json`)
      .then((r) => r.json())
      .then(setData)
      .catch(() => setData([]))
      .finally(() => setLoading(false));
  }, []);
  return { data, loading };
}

export function useCustDev() {
  const [data, setData] = useState<CustDev | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    fetch(`${BASE}data/custdev.json`)
      .then((r) => r.json())
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, []);
  return { data, loading };
}

// Cache for page files (contains up to 50 calls each)
// LRU cache: keep max 20 pages to avoid memory bloat (~10MB)
const MAX_CACHED_PAGES = 20;
const pageCache = new Map<string, CallDetail[]>();
const pageCacheOrder: string[] = [];

function cachePage(pageId: string, data: CallDetail[]) {
  // Remove oldest if at capacity
  if (pageCacheOrder.length >= MAX_CACHED_PAGES) {
    const oldest = pageCacheOrder.shift();
    if (oldest) pageCache.delete(oldest);
  }
  pageCache.set(pageId, data);
  pageCacheOrder.push(pageId);
}

// Cache for individual calls (from index lookups)
const callIndexCache = new Map<string, { page: string; idx_in_page: number }>();

// Lightweight index cache for lookups (only page references, not full data)
let indexCache: CallIndex[] | null = null;
let indexCacheTime = 0;
const INDEX_CACHE_TTL = 5 * 60 * 1000; // 5 minutes

async function ensureIndexLoaded(): Promise<CallIndex[] | null> {
  const now = Date.now();
  if (indexCache && (now - indexCacheTime) < INDEX_CACHE_TTL) {
    return indexCache;
  }
  try {
    const r = await fetch(`${BASE}data/calls/index.json`);
    if (r.ok) {
      indexCache = await r.json();
      indexCacheTime = now;
      return indexCache;
    }
  } catch {
    // Ignore fetch errors
  }
  return null;
}

/** Load a single call by ID.
 *  Optimized to avoid fetching index.json when page info is known.
 *  Falls back to old individual file format for backwards compatibility. */
export function useCallDetail(id: string | null, pageHint?: string) {
  const [data, setData] = useState<CallDetail | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    try {
      let pageId: string | undefined = pageHint;
      let idxInPage = 0;

      // Try call cache first
      const cached = callIndexCache.get(id);
      if (cached) {
        pageId = cached.page;
        idxInPage = cached.idx_in_page;
      }

      // Load page directly if we know it
      if (pageId) {
        const pageData = pageCache.get(pageId);
        if (pageData) {
          const call = pageData[idxInPage];
          if (call?.id === id) {
            setData(call);
            setLoading(false);
            return;
          }
        }
        // Fetch page
        const pageR = await fetch(`${BASE}data/calls/${pageId}.json`);
        if (pageR.ok) {
          const page: CallDetail[] = await pageR.json();
          cachePage(pageId, page);
          const call = page[idxInPage];
          if (call?.id === id) {
            setData(call);
            setLoading(false);
            return;
          }
        }
      }

      // Fallback: search index (expensive, but only when needed)
      const index = await ensureIndexLoaded();
      if (index) {
        const entry = index.find((e) => e.id === id);
        if (entry?.page && typeof entry.idx_in_page === "number") {
          // Cache for next time
          callIndexCache.set(id, { page: entry.page, idx_in_page: entry.idx_in_page });

          const pageData = pageCache.get(entry.page);
          if (pageData) {
            const call = pageData[entry.idx_in_page];
            if (call?.id === id) {
              setData(call);
              setLoading(false);
              return;
            }
          }

          const pageR = await fetch(`${BASE}data/calls/${entry.page}.json`);
          if (pageR.ok) {
            const page: CallDetail[] = await pageR.json();
            cachePage(entry.page, page);
            const call = page[entry.idx_in_page];
            if (call?.id === id) {
              setData(call);
              setLoading(false);
              return;
            }
          }
        }
      }

      // Last resort: old individual file format
      const r = await fetch(`${BASE}data/calls/${id}.json`);
      if (r.ok) {
        setData(await r.json());
      }
    } finally {
      setLoading(false);
    }
  }, [id, pageHint]);

  useEffect(() => {
    load();
  }, [load]);

  return { data, loading };
}

// Re-export formatting helpers so pages can import from one place.
export { pct, fmtDuration, stageLabels } from "./format";

export function stageColor(stage: string | number): string {
  const s = typeof stage === "number" ? `S${stage}` : stage;
  const map: Record<string, string> = {
    S0: "var(--color-stage-s0)", S1: "var(--color-stage-s1)", S2: "var(--color-stage-s2)",
    S3: "var(--color-stage-s3)", S4: "var(--color-stage-s4)",
  };
  return map[s] || "var(--color-ink-muted)";
}

export function useResearch() {
  const [data, setData] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${BASE}data/research.json`)
      .then((r) => {
        if (!r.ok) {
          // Research.json is optional - 404 is OK
          if (r.status === 404) {
            setError(null);
            setData(null);
            return null;
          }
          throw new Error(`HTTP ${r.status}`);
        }
        return r.json();
      })
      .then((d) => {
        if (d !== null) setData(d);
      })
      .catch((e) => {
        setError(e.message);
        setData(null);
      })
      .finally(() => setLoading(false));
  }, []);

  return { data, loading, error };
}
