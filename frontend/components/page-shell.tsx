import type { ReactNode } from "react";

type PageIntroProps = {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
  aside?: ReactNode;
};

type SummaryItem = {
  label: string;
  value: string | number;
  tone?: "default" | "accent" | "success" | "warning";
};

type SummaryStripProps = {
  items: SummaryItem[];
};

type DataPanelProps = {
  title: string;
  description?: string;
  toolbar?: ReactNode;
  children: ReactNode;
};

export function PageIntro({
  title,
  description,
  actions,
  aside,
}: PageIntroProps) {
  return (
    <section className="page-header">
      <div className="page-header-main">
        <div className="page-title-group">
          <h2>{title}</h2>
          {description ? <p>{description}</p> : null}
        </div>
        {actions ? <div className="page-header-actions">{actions}</div> : null}
      </div>
      {aside ? <div className="page-header-meta">{aside}</div> : null}
    </section>
  );
}

export function SummaryStrip({ items }: SummaryStripProps) {
  return (
    <div className="summary-strip">
      {items.map((item) => (
        <div key={`${item.label}-${item.value}`} className={`summary-card ${item.tone ?? "default"}`}>
          <span>{item.label}</span>
          <strong>{item.value}</strong>
        </div>
      ))}
    </div>
  );
}

export function DataPanel({ title, description, toolbar, children }: DataPanelProps) {
  return (
    <section className="panel data-panel">
      <div className="data-panel-header">
        <div className="data-panel-copy">
          <h3>{title}</h3>
          {description ? <p>{description}</p> : null}
        </div>
        {toolbar ? <div className="data-panel-toolbar">{toolbar}</div> : null}
      </div>
      {children}
    </section>
  );
}

export function StatusPill({
  children,
  tone = "default",
}: {
  children: ReactNode;
  tone?: "default" | "success" | "warning" | "danger" | "accent";
}) {
  return <span className={`status-pill ${tone}`}>{children}</span>;
}
