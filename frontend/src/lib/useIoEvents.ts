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

/**
 * Subscribe to the SSE I/O event stream and maintain a map of
 * entry_id → active indicator (read/write animation, auto-expires).
 */
export function useIoEvents(onEvent?: (event: IoEvent) => void) {
  // entry_id → indicator state
  const [indicators, setIndicators] = useState<Record<string, ActiveIndicator>>({});
  const [activeEntries, setActiveEntries] = useState<Set<string>>(new Set());
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

        setIndicators((prev) => ({
          ...prev,
          [data.entry_id]: {
            direction: data.direction,
            expiresAt: now + duration,
          },
        }));

        setActiveEntries((prev) => {
          const next = new Set(prev);
          next.add(data.entry_id);
          return next;
        });

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

  return { indicators, activeEntries };
}
