import { lazy, Suspense, useEffect, useState } from "react";
import { AdminNav, getAdminSections } from "./AdminNav";
import type { AdminSection } from "./AdminNav";
import { TimeTravelAdmin } from "./TimeTravelAdmin";
import { AppLink } from "../AppLink";

const ShareholdersAdmin = lazy(() => import("./ShareholdersAdmin").then((module) => ({ default: module.ShareholdersAdmin })));
const CabinsAdmin = lazy(() => import("./CabinsAdmin").then((module) => ({ default: module.CabinsAdmin })));
const RatesAdmin = lazy(() => import("./RatesAdmin").then((module) => ({ default: module.RatesAdmin })));
const SeasonsAdmin = lazy(() => import("./SeasonsAdmin").then((module) => ({ default: module.SeasonsAdmin })));
const ReservationsAdmin = lazy(() => import("./ReservationsAdmin").then((module) => ({ default: module.ReservationsAdmin })));
const DocumentsAdmin = lazy(() => import("./DocumentsAdmin").then((module) => ({ default: module.DocumentsAdmin })));
const OverviewAdmin = lazy(() => import("./OverviewAdmin").then((module) => ({ default: module.OverviewAdmin })));
const AnalyticsAdmin = lazy(() => import("./AnalyticsAdmin").then((module) => ({ default: module.AnalyticsAdmin })));

interface AdminLayoutProps {
  isAnalytics: boolean;
  isAdmin: boolean;
  isSuperadmin: boolean;
  onTimeTravelChanged?: () => void;
}

const noop = () => {};

export function AdminLayout({ isAnalytics, isAdmin, isSuperadmin, onTimeTravelChanged }: AdminLayoutProps) {
  const [currentSection, setCurrentSection] = useState<AdminSection>("overview");
  const [showMobileSections, setShowMobileSections] = useState(false);
  const [showMobileTimeTravel, setShowMobileTimeTravel] = useState(false);
  const sections = getAdminSections({ isAnalytics, isAdmin, isSuperadmin });
  const isAnalyticsOnly = isAnalytics && !isAdmin && !isSuperadmin;
  const handleTimeTravelChanged = onTimeTravelChanged ?? noop;
  const closeMobileSections = () => setShowMobileSections(false);

  useEffect(() => {
    document.documentElement.classList.add("admin-scroll-page");
    return () => document.documentElement.classList.remove("admin-scroll-page");
  }, []);

  const handleSectionChange = (section: AdminSection) => {
    setCurrentSection(section);
    closeMobileSections();
  };

  const toggleMobileTimeTravel = () => {
    closeMobileSections();
    setShowMobileTimeTravel((current) => !current);
  };

  const renderSection = () => {
    switch (currentSection) {
      case "overview":
        return <OverviewAdmin canSendPaymentEmails={isAdmin || isSuperadmin} />;
      case "analytics":
        return <AnalyticsAdmin />;
      case "reservations":
        if (isAnalyticsOnly) return <OverviewAdmin canSendPaymentEmails={false} />;
        return <ReservationsAdmin />;
      case "cabins":
        if (isAnalyticsOnly) return <OverviewAdmin canSendPaymentEmails={false} />;
        return <CabinsAdmin />;
      case "rates":
        if (isAnalyticsOnly) return <OverviewAdmin canSendPaymentEmails={false} />;
        return <RatesAdmin />;
      case "seasons":
        if (isAnalyticsOnly) return <OverviewAdmin canSendPaymentEmails={false} />;
        return <SeasonsAdmin />;
      case "documents":
        if (isAnalyticsOnly) return <OverviewAdmin canSendPaymentEmails={false} />;
        return <DocumentsAdmin />;
      case "shareholders":
        return isSuperadmin ? <ShareholdersAdmin /> : null;
      default:
        return <OverviewAdmin canSendPaymentEmails={isAdmin || isSuperadmin} />;
    }
  };

  return (
    <div className="admin-layout">
      <header className="admin-header admin-desktop-only">
        <div className="admin-header-topline">
          <div className="admin-header-left">
            <h1>RANGER STATION</h1>
            <span className="admin-district">FOXTON DISTRICT</span>
            <span className="admin-badge-indicator">
              {isSuperadmin ? "Superadmin" : isAnalyticsOnly ? "Analytics" : "Admin"}
            </span>
          </div>
          <div className="admin-header-actions">
            {isSuperadmin ? (
              <div className="admin-time-travel-desktop">
                <TimeTravelAdmin onChanged={handleTimeTravelChanged} />
              </div>
            ) : null}
            <AppLink href="/" className="exit-admin-btn">
              Exit Admin
            </AppLink>
          </div>
        </div>
      </header>
      <div className="admin-content">
        <div className="admin-nav-shell admin-desktop-only">
          <AdminNav
            currentSection={currentSection}
            onSectionChange={handleSectionChange}
            isAnalytics={isAnalytics}
            isAdmin={isAdmin}
            isSuperadmin={isSuperadmin}
          />
        </div>
        <main className="admin-main">
          {isSuperadmin && showMobileTimeTravel ? (
            <div className="admin-mobile-time-travel admin-mobile-only">
              <TimeTravelAdmin onChanged={handleTimeTravelChanged} />
            </div>
          ) : null}
          <Suspense fallback={<div className="admin-loading"><div className="spinner" /></div>}>
            {renderSection()}
          </Suspense>
        </main>
      </div>
      <nav className="admin-mobile-bottom-bar admin-mobile-only">
        <button
          type="button"
          className="admin-mobile-bottom-btn"
          onClick={() => { setShowMobileTimeTravel(false); setShowMobileSections(true); }}
          aria-label="Open admin sections"
        >
          <svg className="admin-mobile-bottom-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="3" y="4" width="18" height="18" rx="2"></rect>
            <line x1="8" y1="9" x2="16" y2="9"></line>
            <line x1="8" y1="13" x2="16" y2="13"></line>
            <line x1="8" y1="17" x2="13" y2="17"></line>
          </svg>
          <span className="admin-mobile-bottom-btn-label">Sections</span>
        </button>
        {isSuperadmin ? (
          <button
            type="button"
            className={`admin-mobile-bottom-btn${showMobileTimeTravel ? " active" : ""}`}
            onClick={toggleMobileTimeTravel}
            aria-label={showMobileTimeTravel ? "Hide time travel" : "Show time travel"}
          >
            <svg className="admin-mobile-bottom-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10"></circle>
              <polyline points="12 6 12 12 16 14"></polyline>
            </svg>
            <span className="admin-mobile-bottom-btn-label">Time Travel</span>
          </button>
        ) : null}
        <AppLink href="/" className="admin-mobile-bottom-btn admin-mobile-bottom-link" aria-label="Exit admin">
          <svg className="admin-mobile-bottom-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
            <polyline points="16 17 21 12 16 7"></polyline>
            <line x1="21" y1="12" x2="9" y2="12"></line>
          </svg>
          <span className="admin-mobile-bottom-btn-label">Exit</span>
        </AppLink>
      </nav>
      {showMobileSections ? (
        <div className="modal-overlay admin-mobile-only" onClick={closeMobileSections}>
          <div className="modal admin-mobile-sections-modal" onClick={(e) => e.stopPropagation()}>
            <h3>Admin Sections</h3>
            <div className="admin-mobile-section-list">
              {sections.map((section) => (
                <button
                  key={section.id}
                  type="button"
                  className={`admin-mobile-section-btn${currentSection === section.id ? " active" : ""}`}
                  onClick={() => handleSectionChange(section.id)}
                >
                  <span className="admin-mobile-section-btn-label">{section.label}</span>
                  {currentSection === section.id ? (
                    <span className="admin-mobile-section-btn-state">Current</span>
                  ) : null}
                </button>
              ))}
            </div>
            <div className="modal-actions">
              <button
                type="button"
                className="cancel-btn"
                onClick={closeMobileSections}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
