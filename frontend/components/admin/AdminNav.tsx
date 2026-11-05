import React from "react";

export type AdminSection = "overview" | "analytics" | "reservations" | "cabins" | "rates" | "seasons" | "documents" | "shareholders";

interface AdminNavProps {
  currentSection: AdminSection;
  onSectionChange: (section: AdminSection) => void;
  isAnalytics: boolean;
  isAdmin: boolean;
  isSuperadmin: boolean;
}

type AdminNavSection = {
  id: AdminSection;
  label: string;
  analyticsVisible?: boolean;
  superadminOnly?: boolean;
};

export interface AdminAccess {
  isAnalytics: boolean;
  isAdmin?: boolean;
  isSuperadmin: boolean;
}

export const adminSections: AdminNavSection[] = [
  { id: "overview", label: "Overview", analyticsVisible: true },
  { id: "analytics", label: "Analytics", analyticsVisible: true },
  { id: "reservations", label: "Reservations" },
  { id: "cabins", label: "Cabins" },
  { id: "rates", label: "Rates" },
  { id: "seasons", label: "Seasons" },
  { id: "documents", label: "Documents" },
  { id: "shareholders", label: "Shareholders", superadminOnly: true },
];

const sectionIcons: Record<AdminSection, React.JSX.Element> = {
  overview: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
    </svg>
  ),
  analytics: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M18 20V10" />
      <path d="M12 20V4" />
      <path d="M6 20v-6" />
    </svg>
  ),
  reservations: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M12 2L2 7l10 5 10-5-10-5z" />
      <path d="M2 17l10 5 10-5" />
      <path d="M2 12l10 5 10-5" />
    </svg>
  ),
  cabins: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M3 21h18" />
      <path d="M5 21V7l7-4 7 4v14" />
      <path d="M9 21v-6h6v6" />
    </svg>
  ),
  rates: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <line x1="12" y1="1" x2="12" y2="23" />
      <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
    </svg>
  ),
  seasons: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
      <line x1="16" y1="2" x2="16" y2="6" />
      <line x1="8" y1="2" x2="8" y2="6" />
      <line x1="3" y1="10" x2="21" y2="10" />
    </svg>
  ),
  documents: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
    </svg>
  ),
  shareholders: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  ),
};

export function getAdminSections(access: AdminAccess) {
  const isAnalyticsOnly = access.isAnalytics && !access.isAdmin && !access.isSuperadmin;
  return adminSections.filter((section) => {
    if (isAnalyticsOnly) return Boolean(section.analyticsVisible);
    return !section.superadminOnly || access.isSuperadmin;
  });
}

export function AdminNav({ currentSection, onSectionChange, isAnalytics, isAdmin, isSuperadmin }: AdminNavProps) {
  const sections = getAdminSections({ isAnalytics, isAdmin, isSuperadmin });

  return (
    <nav className="admin-nav">
      {sections.map((section) => (
        <button
          key={section.id}
          className={`admin-nav-btn ${currentSection === section.id ? "active" : ""}`}
          onClick={() => onSectionChange(section.id)}
        >
          <span className="nav-btn-icon">{sectionIcons[section.id]}</span>
          {section.label}
        </button>
      ))}
    </nav>
  );
}
