import React from "react";

interface AdminMobileRowProps {
  eyebrow: React.ReactNode;
  badge?: React.ReactNode;
  title: React.ReactNode;
  titleClassName?: string;
  meta: React.ReactNode[];
  actions: React.ReactNode;
  muted?: boolean;
}

export function AdminMobileRow({
  eyebrow,
  badge,
  title,
  titleClassName,
  meta,
  actions,
  muted,
}: AdminMobileRowProps) {
  return (
    <article className={`admin-mobile-compact-row${muted ? " is-muted" : ""}`}>
      <div className="admin-mobile-compact-main">
        <div className="admin-mobile-compact-topline">
          <p className="admin-mobile-eyebrow">{eyebrow}</p>
          {badge}
        </div>
        <h3
          className={`admin-mobile-compact-title${titleClassName ? ` ${titleClassName}` : ""}`}
        >
          {title}
        </h3>
        <div className="admin-mobile-compact-meta">
          {meta.map((item, i) => (
            <span key={i}>{item}</span>
          ))}
        </div>
      </div>
      <div className="admin-mobile-compact-actions">{actions}</div>
    </article>
  );
}
