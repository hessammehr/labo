import { useEffect, useRef } from "react";

export type EntryVersionEvent = {
  notebook_id: string;
  entry_id: string;
  version: number;
  updated_at: string;
  timestamp: number;
};

export function useEntryEvents(onEvent: (event: EntryVersionEvent) => void) {
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  useEffect(() => {
    const es = new EventSource("/api/events/entries");

    es.onmessage = (event) => {
      try {
        onEventRef.current(JSON.parse(event.data) as EntryVersionEvent);
      } catch {
        // ignore parse errors
      }
    };

    es.onerror = () => {
      // EventSource reconnects automatically
    };

    return () => {
      es.close();
    };
  }, []);
}
