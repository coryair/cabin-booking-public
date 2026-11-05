import { lazy, Suspense, useState, useEffect, useRef } from "react";
import "./index.css";
import { AppDataProvider, useAppData } from "./context/AppDataContext";
import { TimeTravelBanner } from "./components/TimeTravelBanner";
import { Tooltip } from "./components/Tooltip";
import { createSingleFlightTask } from "./utils/singleFlight";
import { reservationsApi } from "./api/reservations";
import { authApi } from "./api/auth";
import { AppLink } from "./components/AppLink";
import { navigateTo, useBrowserLocation, type BrowserLocation } from "./routing";

const LoginPage = lazy(() => import("./components/LoginPage").then((module) => ({ default: module.LoginPage })));
const AcceptInvitation = lazy(() => import("./components/AcceptInvitation").then((module) => ({ default: module.AcceptInvitation })));
const VerifyMagicLink = lazy(() => import("./components/VerifyMagicLink").then((module) => ({ default: module.VerifyMagicLink })));
const Calendar = lazy(() => import("./components/Calendar").then((module) => ({ default: module.Calendar })));
const AdminLayout = lazy(() => import("./components/admin/AdminLayout").then((module) => ({ default: module.AdminLayout })));
const GuidePage = lazy(() => import("./components/GuidePage").then((module) => ({ default: module.GuidePage })));
const ReservationsModal = lazy(() => import("./components/ReservationsModal").then((module) => ({ default: module.ReservationsModal })));
const BookingSuccess = lazy(() => import("./components/BookingSuccess").then((module) => ({ default: module.BookingSuccess })));
const Tour = lazy(() => import("./components/Tour").then((module) => ({ default: module.Tour })));
const NotificationPreferencesModal = lazy(() => import("./components/NotificationPreferencesModal").then((module) => ({ default: module.NotificationPreferencesModal })));
const CancellationAvailabilityUnsubscribe = lazy(() => import("./components/CancellationAvailabilityUnsubscribe").then((module) => ({ default: module.CancellationAvailabilityUnsubscribe })));

function AppLoading() {
  return (
    <div className="app loading">
      <div className="spinner" />
    </div>
  );
}

function ModalLoading() {
  return (
    <div className="modal-overlay" aria-label="Loading reservations" aria-live="polite">
      <div className="modal-loading">
        <div className="spinner" />
      </div>
    </div>
  );
}

export function App() {
  const location = useBrowserLocation();
  return (
    <AppDataProvider currentPath={location.pathname}>
      <Suspense fallback={<AppLoading />}>
        <AppShell location={location} />
      </Suspense>
    </AppDataProvider>
  );
}

function BookingCancelRedirect({
  adjustmentId,
}: {
  adjustmentId?: string | null;
}) {
  const cancelRef = useRef<(() => Promise<void>) | null>(null);

  if (!cancelRef.current) {
    cancelRef.current = createSingleFlightTask(() => {
      if (adjustmentId) {
        return reservationsApi.cancelGuestAdjustment(Number(adjustmentId));
      }

      return Promise.resolve();
    });
  }

  useEffect(() => {
    let active = true;

    void cancelRef.current!().finally(() => {
      if (active) {
        navigateTo("/", { replace: true });
      }
    });

    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="app loading">
      <div className="spinner" />
    </div>
  );
}

function BookingPaymentRedirect({ reservationId }: { reservationId: string }) {
  const [error, setError] = useState<string | null>(null);
  const [alreadyPaid, setAlreadyPaid] = useState(false);
  const paymentRef = useRef<(() => Promise<void>) | null>(null);

  if (!paymentRef.current) {
    paymentRef.current = async () => {
      const id = Number(reservationId);
      if (!Number.isInteger(id) || id <= 0) {
        throw new Error("This payment link is invalid.");
      }

      const data = await reservationsApi.resumeCheckout(id);

      if (data.status === "paid") {
        setAlreadyPaid(true);
        return;
      }

      if (!data.checkout_url) {
        throw new Error("Payment setup did not return a checkout link.");
      }

      window.location.href = data.checkout_url;
    };
  }

  useEffect(() => {
    let active = true;

    void paymentRef.current!().catch((err) => {
      if (active) {
        setError(err instanceof Error ? err.message : "Unable to open checkout.");
      }
    });

    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-badge">
          <div className="badge-border">
            <svg className="login-mountain-icon" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M3 20L8 10l4 6 4-10 5 14H3z" />
            </svg>
            <h1>Cabin Booking</h1>
          </div>
        </div>

        <div className="magic-link-status">
          {!error && !alreadyPaid && (
            <>
              <div className="spinner" style={{ margin: "0 auto 1rem" }} />
              <p style={{ color: "var(--text-muted)" }}>Opening checkout...</p>
            </>
          )}
          {alreadyPaid && (
            <>
              <p style={{ color: "var(--text-muted)", marginBottom: "1.5rem" }}>
                This reservation is already paid.
              </p>
              <AppLink href="/" className="login-link-button">Back to Calendar</AppLink>
            </>
          )}
          {error && (
            <>
              <p className="login-error" style={{ margin: "0 0 1.5rem" }}>{error}</p>
              <AppLink href="/" className="login-link-button">Back to Calendar</AppLink>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function ActiveSharePicker({ mobile = false }: { mobile?: boolean }) {
  const { allowedShares, activeShareId, setActiveShareId } = useAppData();

  if (allowedShares.length <= 1 || !activeShareId) return null;

  return (
    <label className={`header-share-picker${mobile ? " header-share-picker-mobile" : ""}`}>
      <select
        className="header-share-select"
        value={activeShareId}
        onChange={(e) => {
          const nextShareId = e.target.value;
          if (nextShareId === activeShareId) return;
          setActiveShareId(nextShareId);
        }}
        aria-label="Active booking share"
      >
        {allowedShares.map((share) => (
          <option key={share.share_id} value={share.share_id}>
            {share.share_name}
          </option>
        ))}
      </select>
    </label>
  );
}

function getSafeNextPath(rawNext: string | null): string | null {
  if (!rawNext || !rawNext.startsWith("/") || rawNext.startsWith("//")) return null;
  return rawNext;
}

function RedirectHome() {
  useEffect(() => navigateTo("/", { replace: true }), []);
  return <AppLoading />;
}

function AppShell({ location }: { location: BrowserLocation }) {
  const {
    isAuthenticated,
    isLoading,
    error,
    shareholder,
    login,
    logout,
    isViewer,
    isAnalytics,
    isAdmin,
    isSuperadmin,
    checkAuth,
    sendMagicLink,
    updateCancellationAvailabilityPreference,
    timeTravelActive,
    simulatedDate,
    effectiveToday,
    refreshTimeTravel,
  } = useAppData();
  const [showReservationsModal, setShowReservationsModal] = useState(false);
  const [calendarKey, setCalendarKey] = useState(0);
  const [showTour, setShowTour] = useState(false);
  const [showNotificationPreferences, setShowNotificationPreferences] = useState(false);

  const hasAdminAccess = isAnalytics || isAdmin || isSuperadmin;

  // Show tour on first login (if not yet seen per DB flag)
  useEffect(() => {
    if (isAuthenticated && shareholder && !isViewer && !shareholder.tour_seen) {
      const timer = setTimeout(() => setShowTour(true), 600);
      return () => clearTimeout(timer);
    }
  }, [isAuthenticated, shareholder, isViewer]);

  const handleTourClose = (completed: boolean) => {
    setShowTour(false);
    if (completed) {
      void authApi.markTourSeen();
    }
  };

  const isAdminRoute = location.pathname.startsWith('/admin');
  const isGuideRoute = location.pathname === '/guide';

  const isCancellationUnsubscribeRoute = location.pathname === '/notification-preferences/cancellation-availability/unsubscribe';
  if (isCancellationUnsubscribeRoute) {
    const params = new URLSearchParams(location.search);
    const token = params.get('token');
    if (token) {
      return <CancellationAvailabilityUnsubscribe token={token} />;
    }
    return <RedirectHome />;
  }

  // Handle /invite route before auth gate
  const isInviteRoute = location.pathname === '/invite';
  if (isInviteRoute) {
    const params = new URLSearchParams(location.search);
    const token = params.get('token');
    if (token) {
      return (
        <AcceptInvitation
          token={token}
          onAccepted={() => {
            navigateTo('/', { replace: true });
            void checkAuth(true);
          }}
        />
      );
    }
  }

  // Handle /auth/verify route before auth gate
  const isVerifyRoute = location.pathname === '/auth/verify';
  if (isVerifyRoute) {
    const params = new URLSearchParams(location.search);
    const token = params.get('token');
    const nextPath = getSafeNextPath(params.get('next'));
    if (token) {
      return (
        <VerifyMagicLink
          token={token}
          nextPath={nextPath}
          onVerified={() => {
            navigateTo(nextPath || '/', { replace: true });
            void checkAuth(true);
          }}
        />
      );
    }
  }

  if (isLoading) {
    return (
      <div className="app loading">
        <div className="spinner" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <LoginPage onLogin={login} onSendMagicLink={sendMagicLink} error={error} isLoading={isLoading} />;
  }

  // Handle /booking/pay route after auth gate so email links can sign in first.
  const isBookingPayRoute = location.pathname === '/booking/pay';
  if (isBookingPayRoute) {
    const params = new URLSearchParams(location.search);
    const reservationId = params.get('reservation_id');
    if (reservationId) {
      return <BookingPaymentRedirect reservationId={reservationId} />;
    }
    return <RedirectHome />;
  }

  // Handle /booking/success route
  const isBookingSuccessRoute = location.pathname === '/booking/success';
  if (isBookingSuccessRoute) {
    const params = new URLSearchParams(location.search);
    const reservationId = params.get('reservation_id');
    const adjustmentId = params.get('adjustment_id');
    if (reservationId) {
      return (
        <BookingSuccess
          reservationId={reservationId}
          adjustmentId={adjustmentId}
          onReturn={() => {
            navigateTo('/', { replace: true });
          }}
        />
      );
    }
  }

  // Handle /booking/cancel route - user returned from Stripe without paying
  const isBookingCancelRoute = location.pathname === '/booking/cancel';
  if (isBookingCancelRoute) {
    const params = new URLSearchParams(location.search);
    const reservationId = params.get('reservation_id');
    const adjustmentId = params.get('adjustment_id');
    if (reservationId || adjustmentId) {
      return <BookingCancelRedirect adjustmentId={adjustmentId} />;
    }
    return <RedirectHome />;
  }

  if (isAdminRoute && hasAdminAccess) {
    return (
      <>
        <TimeTravelBanner isActive={timeTravelActive} simulatedDate={simulatedDate} />
        <AdminLayout
          isAnalytics={isAnalytics}
          isAdmin={isAdmin}
          isSuperadmin={isSuperadmin}
          onTimeTravelChanged={refreshTimeTravel}
        />
      </>
    );
  }

  return (
    <div className={`app${isGuideRoute ? ' app-scrollable' : ' app-calendar-scrollable'}`}>
      <TimeTravelBanner isActive={timeTravelActive} simulatedDate={simulatedDate} />
      <header className="app-header">
        <div className="header-top-bar">
          <div className="header-brand">
            <h1>Cabin Booking</h1>
            <span className="header-location">FOXTON, CO - SOUTH PLATTE RIVER</span>
          </div>
          {/* Desktop header with full user info */}
          <div className="header-user desktop-only">
            {shareholder && (
              <span className="header-user-name">
                {shareholder.first_name} {shareholder.last_name}
                {!shareholder.can_access_multiple_shares && (
                  <> | {shareholder.share_name || shareholder.share}</>
                )}
              </span>
            )}
            <ActiveSharePicker />
            {isGuideRoute ? (
              <Tooltip text="View the reservation calendar" position="bottom">
                <AppLink href="/" className="admin-button">
                  Calendar
                </AppLink>
              </Tooltip>
            ) : (
              <Tooltip text="How reservations work, round schedule, and rules" position="bottom">
                <AppLink href="/guide" className="admin-button" data-tour="guide-link">
                  Booking Guide
                </AppLink>
              </Tooltip>
            )}
            {!isViewer && (
              <Tooltip text="View upcoming and past trips" position="bottom">
                <button className="admin-button" onClick={() => setShowReservationsModal(true)} data-tour="reservations-link">
                  My Reservations
                </button>
              </Tooltip>
            )}
            {hasAdminAccess && (
              <Tooltip text="Manage cabins, rates, and reservations" position="bottom">
                <AppLink href="/admin" className="admin-button">
                  Admin Panel
                </AppLink>
              </Tooltip>
            )}
            <Tooltip text="Manage email notifications" position="bottom">
              <button className="admin-button" onClick={() => setShowNotificationPreferences(true)}>
                Notifications
              </button>
            </Tooltip>
            {!isGuideRoute && !isViewer && (
              <Tooltip text="Take a guided tour" position="bottom">
                <button className="tour-launch-btn" onClick={() => setShowTour(true)} aria-label="Take a tour">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <circle cx="12" cy="12" r="10" />
                    <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
                    <line x1="12" y1="17" x2="12.01" y2="17" />
                  </svg>
                </button>
              </Tooltip>
            )}
            <button onClick={logout} className="logout-button">
              Log Out
            </button>
          </div>
          {/* Mobile header with avatar */}
          <div className="header-user-mobile mobile-only">
            <ActiveSharePicker mobile />
            {shareholder && (
              <span className="user-avatar">
                {shareholder.first_name?.charAt(0) || '?'}
              </span>
            )}
          </div>
        </div>
      </header>

      <main>
        {isGuideRoute ? (
          <GuidePage />
        ) : (
          <Calendar key={calendarKey} effectiveToday={effectiveToday} />
        )}
      </main>

      {/* Mobile bottom navigation */}
      <nav className="mobile-bottom-nav mobile-only">
        {isGuideRoute ? (
          <AppLink href="/" className="nav-item">
            <svg className="nav-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
              <line x1="16" y1="2" x2="16" y2="6"></line>
              <line x1="8" y1="2" x2="8" y2="6"></line>
              <line x1="3" y1="10" x2="21" y2="10"></line>
              <line x1="3" y1="14" x2="21" y2="14"></line>
              <line x1="3" y1="18" x2="21" y2="18"></line>
            </svg>
            <span className="nav-label">Calendar</span>
          </AppLink>
        ) : (
          <AppLink href="/guide" className="nav-item" data-tour="guide-link-mobile">
            <svg className="nav-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="16" x2="12" y2="12"></line>
              <line x1="12" y1="8" x2="12.01" y2="8"></line>
            </svg>
            <span className="nav-label">Booking Guide</span>
          </AppLink>
        )}
        {!isViewer && (
          <button
            className="nav-item"
            onClick={() => setShowReservationsModal(true)}
          >
            <svg className="nav-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
              <line x1="16" y1="2" x2="16" y2="6"></line>
              <line x1="8" y1="2" x2="8" y2="6"></line>
              <line x1="3" y1="10" x2="21" y2="10"></line>
            </svg>
            <span className="nav-label">My Reservations</span>
          </button>
        )}
        {hasAdminAccess && (
          <AppLink href="/admin" className="nav-item">
            <svg className="nav-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="3"></circle>
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
            </svg>
            <span className="nav-label">Admin</span>
          </AppLink>
        )}
        <button className="nav-item" onClick={() => setShowNotificationPreferences(true)}>
          <svg className="nav-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9"></path>
            <path d="M13.73 21a2 2 0 0 1-3.46 0"></path>
          </svg>
          <span className="nav-label">Notifications</span>
        </button>
        <button className="nav-item" onClick={logout}>
          <svg className="nav-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
            <polyline points="16 17 21 12 16 7"></polyline>
            <line x1="21" y1="12" x2="9" y2="12"></line>
          </svg>
          <span className="nav-label">Log Out</span>
        </button>
      </nav>

      {showReservationsModal && (
        <Suspense fallback={<ModalLoading />}>
          <ReservationsModal
            onClose={() => setShowReservationsModal(false)}
            onReservationDeleted={() => setCalendarKey(k => k + 1)}
            effectiveToday={effectiveToday}
          />
        </Suspense>
      )}

      {showNotificationPreferences && shareholder && (
        <Suspense fallback={<ModalLoading />}>
          <NotificationPreferencesModal
            enabled={shareholder.cancellation_availability_emails_enabled}
            onClose={() => setShowNotificationPreferences(false)}
            onSave={updateCancellationAvailabilityPreference}
          />
        </Suspense>
      )}

      {showTour && !isGuideRoute && !isViewer && (
        <Tour onClose={handleTourClose} />
      )}
    </div>
  );
}

export default App;
