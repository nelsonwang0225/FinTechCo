import { useEffect, useRef, useState, type ReactNode } from "react";
import { IconArrowDown, IconArrowUp, IconArrowUpDown } from "../layout/icons";

export interface Column<Row> {
  key: string;
  header: ReactNode;
  render: (row: Row) => ReactNode;
  align?: "left" | "right";
  /** Sort key sent to the API when this header is clicked; omit for unsortable columns. */
  sortKey?: string;
  width?: string;
  /** Extra class on every cell of this column, e.g. "primary" for the dominant field or "secondary" for ids. */
  className?: string;
}

export interface SortState {
  sort: string;
  dir: "asc" | "desc";
}

export interface DataTableProps<Row> {
  columns: Column<Row>[];
  rows: Row[];
  rowKey: (row: Row) => string;
  caption: string;
  sort?: SortState;
  onSort?: (sortKey: string) => void;
  onRowClick?: (row: Row) => void;
  rowHref?: (row: Row) => string | undefined;
  loading?: boolean;
}

function cellClass<Row>(col: Column<Row>): string | undefined {
  const parts = [col.align === "right" ? "money" : "", col.className ?? ""].filter(Boolean);
  return parts.length ? parts.join(" ") : undefined;
}

/**
 * Plain table primitive. Money columns pass `align: "right"` so header and cells share tabular alignment.
 * Row navigation is a real link in the first cell (keyboard reachable) plus an optional whole-row click.
 * Headers stick below the top bar while a long table scrolls.
 */
export function DataTable<Row>({ columns, rows, rowKey, caption, sort, onSort, onRowClick, loading }: DataTableProps<Row>) {
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const [scrolls, setScrolls] = useState(false);
  // When the table is wider than its container, let the wrap scroll sideways so no column becomes unreachable.
  useEffect(() => {
    const el = wrapRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const check = () => {
      const table = el.querySelector("table");
      if (!table) return;
      setScrolls(table.getBoundingClientRect().width > el.clientWidth + 1);
    };
    check();
    const observer = new ResizeObserver(check);
    observer.observe(el);
    return () => observer.disconnect();
  }, [rows, columns.length]);
  return (
    <div ref={wrapRef} className={`table-wrap${scrolls ? " table-wrap-scroll" : ""}${loading ? " table-loading" : ""}`} aria-busy={loading || undefined}>
      <table className="table">
        <caption className="visually-hidden">{caption}</caption>
        <thead>
          <tr>
            {columns.map((col) => {
              const sortable = Boolean(col.sortKey && onSort);
              const active = sortable && sort?.sort === col.sortKey;
              const ariaSort = active ? (sort?.dir === "asc" ? "ascending" : "descending") : undefined;
              return (
                <th key={col.key} scope="col" className={col.align === "right" ? "money" : undefined} style={col.width ? { width: col.width } : undefined} aria-sort={ariaSort}>
                  {sortable ? (
                    <button type="button" className={`th-sort${active ? " active" : ""}`} onClick={() => col.sortKey && onSort?.(col.sortKey)}>
                      {col.header}
                      <span className="th-sort-mark" aria-hidden="true">
                        {active ? sort?.dir === "asc" ? <IconArrowUp /> : <IconArrowDown /> : <IconArrowUpDown />}
                      </span>
                    </button>
                  ) : (
                    col.header
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)} className={onRowClick ? "row-clickable" : undefined} onClick={onRowClick ? () => onRowClick(row) : undefined}>
              {columns.map((col) => (
                <td key={col.key} className={cellClass(col)}>
                  {col.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
