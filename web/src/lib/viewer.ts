"use client";

import { useEffect, useState } from "react";

/**
 * Who is looking: the owner, or a visitor.
 *
 * The page only uses this to hide controls a visitor could not use anyway. The
 * rules themselves live in the proxy and the API; hiding a button is a courtesy,
 * not the lock.
 *
 * Null until known, and callers treat null as "not the owner", so a visitor never
 * sees the owner's buttons flash up while the answer is on its way.
 */
export type Viewer = "owner" | "reader" | "public";

export function useViewer(): Viewer | null {
  const [viewer, setViewer] = useState<Viewer | null>(null);

  useEffect(() => {
    let cancelled = false;

    fetch("/api/viewer", { cache: "no-store" })
      .then((response) => (response.ok ? response.json() : { viewer: "public" }))
      .then((body: { viewer?: Viewer }) => {
        if (!cancelled) setViewer(body.viewer ?? "public");
      })
      .catch(() => {
        if (!cancelled) setViewer("public");
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return viewer;
}
