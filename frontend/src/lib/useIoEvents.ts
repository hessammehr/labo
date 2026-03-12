import { useEffect, useRef, useState } from "react";

export type IoEvent = {
  resource_type: "notebook" | "entry";
  resource_id: string;
  entry_id: string;
  filename: string;
  direction: "read" | "write";
  timestamp: number;
};

type ActiveIndicator = {
  direction: "read" | "write";
  expiresAt: number;
};

/** Unique key for a specific file. */
export function ioKey(entryId: string, filename: string) {
  return `${entryId}/${filename}`;
}

/**
 * Subscribe to the SSE I/O event stream and maintain a map of
 * entryId/filename → active indicator (read/write animation, auto-expires).
 */
export function useIoEvents(onEvent?: (event: IoEvent) => void) {
  const [indicators, setIndicators] = useState<Record<string, ActiveIndicator>>({});
  const eventSourceRef = useRef<EventSource | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  useEffect(() => {
    const es = new EventSource("/api/events/io");
    eventSourceRef.current = es;

    es.onmessage = (event) => {
      try {
        const data: IoEvent = JSON.parse(event.data);
        const now = Date.now();
        const duration = 1200; // ms to show the animation
        const key = ioKey(data.entry_id, data.filename);

        setIndicators((prev) => ({
          ...prev,
          [key]: {
            direction: data.direction,
            expiresAt: now + duration,
          },
        }));

        onEventRef.current?.(data);
      } catch {
        // ignore parse errors
      }
    };

    es.onerror = () => {
      // EventSource reconnects automatically
    };

    // Sweep expired indicators every 500ms
    timerRef.current = setInterval(() => {
      const now = Date.now();
      setIndicators((prev) => {
        const next: Record<string, ActiveIndicator> = {};
        let changed = false;
        for (const [id, ind] of Object.entries(prev)) {
          if (ind.expiresAt > now) {
            next[id] = ind;
          } else {
            changed = true;
          }
        }
        return changed ? next : prev;
      });
    }, 500);

    return () => {
      es.close();
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  return { indicators };
}
