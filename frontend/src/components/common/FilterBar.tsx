import { useQuery } from "@tanstack/react-query";
import { CalendarRange, Filter } from "lucide-react";
import { Select } from "@/components/ui/primitives";
import { DAY_OPTIONS, useGlobalFilters } from "@/lib/filters";
import { api } from "@/lib/api";
import type { Overview } from "@/lib/types";

/** Date-range + language + data-source selectors shared by analytical pages (URL-backed). */
export function FilterBar({ showLanguage = true, showSource = true }: { showLanguage?: boolean; showSource?: boolean }) {
  const { filters, setFilter } = useGlobalFilters();
  const { data } = useQuery({
    queryKey: ["languages-filter"],
    queryFn: ({ signal }) => api.get<Overview>("/dashboard/overview?days=365", signal),
    staleTime: 120_000,
    enabled: showLanguage,
  });
  const languages = data?.languages.map((l) => l.language) ?? [];
  return (
    <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Filters">
      <div className="flex items-center gap-1.5 rounded-xl border border-white/10 bg-ink-900/60 px-2">
        <CalendarRange className="h-4 w-4 text-slate-500" />
        <Select aria-label="Date range" className="border-0 bg-transparent px-1 focus:ring-0" value={filters.days} onChange={(e) => setFilter("days", e.target.value)}>
          {DAY_OPTIONS.map((d) => <option key={d} value={d} className="bg-ink-900">Last {d} days</option>)}
        </Select>
      </div>
      {showLanguage && (
        <div className="flex items-center gap-1.5 rounded-xl border border-white/10 bg-ink-900/60 px-2">
          <Filter className="h-4 w-4 text-slate-500" />
          <Select aria-label="Language" className="border-0 bg-transparent px-1 focus:ring-0" value={filters.language} onChange={(e) => setFilter("language", e.target.value)}>
            <option value="" className="bg-ink-900">All languages</option>
            {languages.map((l) => <option key={l} value={l} className="bg-ink-900">{l}</option>)}
          </Select>
        </div>
      )}
      {showSource && (
        <Select aria-label="Data source" value={filters.dataSource} onChange={(e) => setFilter("source", e.target.value)}>
          <option value="" className="bg-ink-900">All sources</option>
          <option value="github" className="bg-ink-900">Live GitHub only</option>
          <option value="synthetic" className="bg-ink-900">Demo (synthetic) only</option>
        </Select>
      )}
    </div>
  );
}
