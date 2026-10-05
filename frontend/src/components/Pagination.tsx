import { IconChevronLeft, IconChevronRight } from "../layout/icons";
import { formatCount } from "../lib/format";

export function Pagination({ page, pageSize, total, onPage }: { page: number; pageSize: number; total: number; onPage: (page: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const first = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const last = Math.min(total, page * pageSize);
  return (
    <nav className="pagination" aria-label="Pagination">
      <span className="pagination-summary num">
        {total === 0 ? "No results" : `${formatCount(first)}–${formatCount(last)} of ${formatCount(total)}`}
      </span>
      <div className="pagination-controls">
        <button type="button" className="btn btn-sm" onClick={() => onPage(page - 1)} disabled={page <= 1}>
          <IconChevronLeft />
          Previous
        </button>
        <span className="num muted">
          Page {formatCount(page)} of {formatCount(pages)}
        </span>
        <button type="button" className="btn btn-sm" onClick={() => onPage(page + 1)} disabled={page >= pages}>
          Next
          <IconChevronRight />
        </button>
      </div>
    </nav>
  );
}
