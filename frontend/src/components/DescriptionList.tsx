import type { ReactNode } from "react";

export interface DescriptionItem {
  term: string;
  value: ReactNode;
}

export function DescriptionList({ items, columns = 3 }: { items: DescriptionItem[]; columns?: 2 | 3 | 4 }) {
  return (
    <dl className={`dl dl-${columns}`}>
      {items.map((item) => (
        <div key={item.term} className="dl-item">
          <dt>{item.term}</dt>
          <dd>{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}
