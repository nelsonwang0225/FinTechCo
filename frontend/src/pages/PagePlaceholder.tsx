import { PageHeader } from "../layout/PageHeader";

// Temporary route body used while sections are being built; every section replaces it.
export function PagePlaceholder({ title }: { title: string }) {
  return (
    <>
      <PageHeader title={title} />
      <div className="card" role="status" aria-live="polite">
        <p className="muted">Loading…</p>
      </div>
    </>
  );
}
