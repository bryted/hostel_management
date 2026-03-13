"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import type { SearchResponse, SearchResultItem } from "../lib/api";
import { getJson } from "../lib/client-api";

type Props = {
  isAdmin: boolean;
};

function resultGroupLabel(type: string): string {
  if (type === "tenant") return "Tenants";
  if (type === "invoice") return "Invoices";
  if (type === "receipt") return "Receipts";
  if (type === "payment") return "Payments";
  if (type === "bed") return "Beds";
  if (type === "room") return "Rooms";
  if (type === "allocation") return "Allocations";
  if (type === "user") return "Users";
  return "Quick links";
}

export function GlobalSearch({ isAdmin }: Props) {
  const router = useRouter();
  const pathname = usePathname();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);

  useEffect(() => {
    setResults([]);
    setActiveIndex(0);
  }, [pathname]);

  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setResults([]);
      setLoading(false);
      setActiveIndex(0);
      return;
    }
    setLoading(true);
    const timeout = window.setTimeout(async () => {
      try {
        const response = await getJson<SearchResponse>(`/search?q=${encodeURIComponent(trimmed)}`);
        setResults(response.results);
        setActiveIndex(0);
      } catch {
        setResults([]);
        setActiveIndex(0);
      } finally {
        setLoading(false);
      }
    }, 180);
    return () => window.clearTimeout(timeout);
  }, [query]);

  const groupedResults = useMemo(() => {
    const groups = new Map<string, SearchResultItem[]>();
    for (const result of results) {
      const label = resultGroupLabel(result.type);
      groups.set(label, [...(groups.get(label) ?? []), result]);
    }
    return Array.from(groups.entries());
  }, [results]);

  function openResult(index: number) {
    const target = results[index];
    if (!target) return;
    setQuery("");
    setResults([]);
    setActiveIndex(0);
    router.push(target.href);
  }

  return (
    <div className="global-search">
      <label className="search-field">
        <span className="sr-only">Global search</span>
        <input
          autoComplete="off"
          name="global_search"
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown") {
              event.preventDefault();
              setActiveIndex((current) => Math.min(current + 1, Math.max(results.length - 1, 0)));
            } else if (event.key === "ArrowUp") {
              event.preventDefault();
              setActiveIndex((current) => Math.max(current - 1, 0));
            } else if (event.key === "Enter" && results.length) {
              event.preventDefault();
              openResult(activeIndex);
            } else if (event.key === "Escape") {
              setQuery("");
              setResults([]);
              setActiveIndex(0);
            }
          }}
          placeholder={isAdmin ? "Search tenant, invoice, receipt, payment, bed, room, allocation" : "Search tenant, invoice, receipt, payment"}
        />
      </label>
      {(loading || results.length > 0 || query.trim().length >= 2) ? (
        <div className="search-results">
          {!loading && results.length ? <p className="small">{results.length} result(s)</p> : null}
          {loading ? <p className="small">Searching...</p> : null}
          {!loading && !results.length ? <p className="small">No matching records.</p> : null}
          {!loading
            ? groupedResults.map(([label, items]) => (
                <div key={label} className="search-group">
                  <span className="search-group-label">{label}</span>
                  <div className="search-group-items">
                    {items.map((result) => {
                      const resultIndex = results.findIndex(
                        (candidate) =>
                          candidate.id === result.id &&
                          candidate.type === result.type &&
                          candidate.href === result.href,
                      );
                      return (
                        <Link
                          key={`${result.type}-${result.id}-${result.href}`}
                          className={`search-result ${resultIndex === activeIndex ? "active" : ""}`}
                          href={result.href}
                          onMouseEnter={() => setActiveIndex(resultIndex)}
                          onClick={() => {
                            setQuery("");
                            setResults([]);
                            setActiveIndex(0);
                          }}
                        >
                          <strong>{result.title}</strong>
                          {result.subtitle ? <span>{result.subtitle}</span> : null}
                        </Link>
                      );
                    })}
                  </div>
                </div>
              ))
            : null}
        </div>
      ) : null}
    </div>
  );
}
