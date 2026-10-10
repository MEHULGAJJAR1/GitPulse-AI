import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";

export const DAY_OPTIONS = [7, 30, 90, 180, 365] as const;
export type DataSourceFilter = "" | "github" | "synthetic";

export interface GlobalFilters {
  days: number;
  language: string;
  dataSource: DataSourceFilter;
}

/** Date-range and facet filters live in the URL, so every view is shareable and reload-safe. */
export function useGlobalFilters() {
  const [params, setParams] = useSearchParams();
  const raw = Number(params.get("days") ?? 30);
  const days = (DAY_OPTIONS as readonly number[]).includes(raw) ? raw : 30;
  const language = params.get("language") ?? "";
  const dataSource = (params.get("source") ?? "") as DataSourceFilter;
  const setFilter = useCallback(
    (key: "days" | "language" | "source", value: string | number) => {
      setParams((prev) => {
        const next = new URLSearchParams(prev);
        if (value === "" || value === undefined || value === null) next.delete(key);
        else next.set(key, String(value));
        return next;
      }, { replace: true });
    },
    [setParams],
  );
  const filters: GlobalFilters = { days, language, dataSource };
  return { filters, setFilter, params };
}
