import type { ReactNode } from "react";

export interface Column<Row> {
  key: string;
  header: ReactNode;
  render: (row: Row) => ReactNode;
  align?: "left" | "right";
  /** Sort key sent to the API when this header is clicked; omit for unsortable columns. */
  sortKey?: string;
  width?: string;
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

/**
 * Plain table primitive. Money columns pass `align: "right"` so header and cells share tabular alignment.
 * Row navigation is a real link in the first cell (keyboard reachable) plus an optional whole-row click.
 */
export function DataTable<Row>({ columns, rows, rowKey, caption, sort, onSort, onRowClick, loading }: DataTableProps<Row>) {
  return (
    <div className={`table-wrap${loading ? " table-loading" : ""}`} aria-busy={loading || undefined}>
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
                        {active ? (sort?.dir === "asc" ? "↑" : "↓") : ""}
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
                <td key={col.key} className={col.align === "right" ? "money" : undefined}>
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
