import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Calls `load()` straight away, then again every `intervalMs`, so the screen stays live:
 * a payment made in the USSD simulator shows up here within a few seconds.
 *
 * Returns { data, error, updatedAt, reload }.
 */
export function usePolling(load, intervalMs = 3000) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [updatedAt, setUpdatedAt] = useState(null);
  const loadRef = useRef(load);
  loadRef.current = load;

  const reload = useCallback(async () => {
    try {
      setData(await loadRef.current());
      setError(null);
      setUpdatedAt(new Date());
    } catch (err) {
      setError(err);
    }
  }, []);

  useEffect(() => {
    reload();
    const timer = setInterval(reload, intervalMs);
    return () => clearInterval(timer); // stop polling when the page is left
  }, [reload, intervalMs]);

  return { data, error, updatedAt, reload };
}
