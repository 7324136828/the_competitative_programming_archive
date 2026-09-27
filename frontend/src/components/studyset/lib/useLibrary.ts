/**
 * Hook backing every viewer: fetch the manifest, load one kind, track selection.
 * Equivalent to LibraryApp.refresh + LibraryApp.selected in launcher_common.py.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchManifest, loadKind, type Loaded } from "./content";
import type { Kind, ManifestEntry } from "../types";

export interface LibraryState<T> {
  documents: Loaded<T>[];
  errors: string[];
  loading: boolean;
  selectedIndex: number;
  select: (index: number) => void;
  selected: Loaded<T> | null;
  reload: () => void;
}

export function useLibrary<T>(
  kind: Kind,
  parse: (raw: Record<string, unknown>, where: string) => T,
): LibraryState<T> {
  const [documents, setDocuments] = useState<Loaded<T>[]>([]);
  const [errors, setErrors] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const selectedEntry = useRef<ManifestEntry | null>(null);
  const [nonce, setNonce] = useState(0);

  // `parse` is typically an inline function; pinning it here keeps the effect
  // from re-running on every render.
  const parseRef = useMemo(() => parse, [kind]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    (async () => {
      try {
        const manifest = await fetchManifest();
        const result = await loadKind<T>(kind, manifest, parseRef);
        if (cancelled) return;
        setDocuments(result.documents);
        setErrors(result.errors);
        const previous = selectedEntry.current;
        const nextIndex = previous
          ? result.documents.findIndex((item) =>
              item.entry.file === previous.file && item.entry.subject === previous.subject)
          : 0;
        setSelectedIndex(Math.max(0, nextIndex));
        selectedEntry.current = result.documents[Math.max(0, nextIndex)]?.entry ?? null;
      } catch (error) {
        if (cancelled) return;
        setDocuments([]);
        setErrors([(error as Error).message]);
        selectedEntry.current = null;
        setSelectedIndex(0);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [kind, parseRef, nonce]);

  const select = useCallback((index: number) => {
    selectedEntry.current = documents[index]?.entry ?? null;
    setSelectedIndex(index);
  }, [documents]);
  const reload = useCallback(() => setNonce((n) => n + 1), []);

  return {
    documents,
    errors,
    loading,
    selectedIndex,
    select,
    selected: documents[selectedIndex] ?? null,
    reload,
  };
}
