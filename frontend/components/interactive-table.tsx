"use client";

import { useMemo, useState } from "react";

import type { TableRow } from "../lib/api";

type Props = {
  rows: TableRow[];
  emptyText: string;
  searchPlaceholder?: string;
};

function normalize(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "";
  return String(value).toLowerCase();
}

export function InteractiveTable({ rows, emptyText, searchPlaceholder = "Filter rows" }: Props) {
  const [filter, setFilter] = useState("");
  const [sortColumn, setSortColumn] = useState<string | null>(rows[0] ? Object.keys(rows[0])[0] : null);
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("asc");

  const columns = rows[0] ? Object.keys(rows[0]) : [];

  const filteredRows = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    const baseRows = !needle
      ? rows
      : rows.filter((row) =>
          Object.values(row).some((value) => normalize(value).includes(needle)),
        );
    if (!sortColumn) return baseRows;
    return [...baseRows].sort((left, right) => {
      const leftValue = normalize(left[sortColumn]);
      const rightValue = normalize(right[sortColumn]);
      const comparison = leftValue.localeCompare(rightValue, undefined, { numeric: true });
      return sortDirection === "asc" ? comparison : -comparison;
    });
  }, [filter, rows, sortColumn, sortDirection]);

  if (!rows.length) {
    return <p className="small">{emptyText}</p>;
  }

  return (
    <div className="stack tight">
      <div className="toolbar">
        <input
          autoComplete="off"
          name="table_filter"
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
          placeholder={searchPlaceholder}
        />
        <span className="small">{filteredRows.length} row(s)</span>
      </div>
      <table className="table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>
                <button
                  className="table-sort"
                  onClick={() => {
                    if (sortColumn === column) {
                      setSortDirection((current) => (current === "asc" ? "desc" : "asc"));
                    } else {
                      setSortColumn(column);
                      setSortDirection("asc");
                    }
                  }}
                  type="button"
                >
                  <span>{column}</span>
                  <span>
                    {sortColumn === column
                      ? sortDirection === "asc"
                        ? "\u2191"
                        : "\u2193"
                      : "\u2195"}
                  </span>
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {filteredRows.length ? (
            filteredRows.map((row, index) => (
              <tr key={`${index}-${columns.join("-")}`}>
                {columns.map((column) => (
                  <td key={column}>{row[column] ?? "-"}</td>
                ))}
              </tr>
            ))
          ) : (
            <tr>
              <td className="small" colSpan={columns.length}>
                No rows match the current filter.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
