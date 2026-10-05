import type { ReactNode } from "react";

/**
 * Title plus one contextual sentence, with the page's actions on the right.
 * `above` renders a breadcrumb or back link over the title on detail pages.
 */
export function PageHeader({ title, subtitle, actions, above }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode; above?: ReactNode }) {
  return (
    <header className="page-header">
      <div className="page-header-text">
        {above ? <div className="breadcrumb">{above}</div> : null}
        <h1 className="page-title">{title}</h1>
        {subtitle ? <p className="page-subtitle">{subtitle}</p> : null}
      </div>
      {actions ? <div className="page-actions">{actions}</div> : null}
    </header>
  );
}
