import { useCallback, useEffect, useRef, useState } from "react";
import { getZoom } from "../utils";

interface TourStep {
  target: string; // CSS selector
  title: string;
  content: string;
  placement: "top" | "bottom";
}

const TOUR_STEPS: TourStep[] = [
  {
    target: "",
    title: "Welcome to Cabin Booking",
    content:
      "Let's take a quick tour of how to book your cabin reservations. This will only take a moment.",
    placement: "bottom",
  },
  {
    target: "[data-tour='status-banner']",
    title: "Booking Status",
    content:
      "This banner shows the current booking round, your priority position, and how many nights you've used. Tap it for more details.",
    placement: "bottom",
  },
  {
    target: "[data-tour='calendar-legend']",
    title: "Calendar Legend",
    content:
      "The legend shows how reservations appear on the calendar. Each cabin has its own color so you can see availability at a glance.",
    placement: "bottom",
  },
  {
    target: ".calendar-month-anchor:first-child",
    title: "Select Your Dates",
    content:
      "Tap a date to start your selection, then tap another date to set your range. The booking form will open automatically.",
    placement: "bottom",
  },
  {
    target: "[data-tour='guide-link'], [data-tour='guide-link-mobile']",
    title: "Booking Guide",
    content:
      "Need more details? The Booking Guide explains round schedules, priority order, night limits, and all the rules.",
    placement: "bottom",
  },
  {
    target: "[data-tour='reservations-link'], .mobile-bottom-nav .nav-item:nth-child(2)",
    title: "Your Reservations",
    content:
      "View all your upcoming and past reservations here. You can also cancel bookings or adjust guest counts.",
    placement: "bottom",
  },
];

interface TourProps {
  onClose: (completed: boolean) => void;
}

interface SpotlightRect {
  top: number;
  left: number;
  width: number;
  height: number;
}

interface TooltipPosition {
  top: number;
  left: number;
}

function getSpotlightRect(el: Element): SpotlightRect {
  const rect = el.getBoundingClientRect();
  const zoom = getZoom();
  const pad = 8;
  return {
    top: rect.top / zoom - pad,
    left: rect.left / zoom - pad,
    width: rect.width / zoom + pad * 2,
    height: rect.height / zoom + pad * 2,
  };
}

function getTooltipPosition(
  spotlight: SpotlightRect,
  placement: "top" | "bottom",
  tooltipEl: HTMLElement | null
): TooltipPosition {
  const gap = 16;
  const tooltipWidth = tooltipEl?.offsetWidth || 320;
  const tooltipHeight = tooltipEl?.offsetHeight || 160;
  const zoom = getZoom();
  const vw = window.innerWidth / zoom;
  const vh = window.innerHeight / zoom;

  // If target is in the bottom third of the viewport and placement is "bottom",
  // flip to "top" so the tooltip doesn't cover the target (e.g. mobile bottom nav)
  let effectivePlacement = placement;
  if (placement === "bottom" && spotlight.top + spotlight.height > vh * 0.67) {
    effectivePlacement = "top";
  }

  let top = 0;
  let left = 0;

  switch (effectivePlacement) {
    case "bottom":
      top = spotlight.top + spotlight.height + gap;
      left = spotlight.left + spotlight.width / 2 - tooltipWidth / 2;
      break;
    case "top":
      top = spotlight.top - tooltipHeight - gap;
      left = spotlight.left + spotlight.width / 2 - tooltipWidth / 2;
      break;
  }

  // Clamp horizontal
  if (left < 12) left = 12;
  if (left + tooltipWidth > vw - 12) left = vw - tooltipWidth - 12;

  // Clamp vertical
  if (top < 12) top = 12;
  if (top + tooltipHeight > vh - 12) top = vh - tooltipHeight - 12;

  return { top, left };
}

export function Tour({ onClose }: TourProps) {
  const [currentStep, setCurrentStep] = useState(0);
  const [spotlight, setSpotlight] = useState<SpotlightRect | null>(null);
  const [tooltipPos, setTooltipPos] = useState<TooltipPosition | null>(null);
  const [isVisible, setIsVisible] = useState(false);
  const [isExiting, setIsExiting] = useState(false);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const step: TourStep = TOUR_STEPS[currentStep] ?? TOUR_STEPS[0]!;

  const findTargetElement = useCallback((target: string): Element | null => {
    const candidates = target.split(",").map((s) => s.trim()).filter(Boolean);
    for (const selector of candidates) {
      const candidate = document.querySelector(selector);
      if (candidate && candidate.getBoundingClientRect().width > 0) {
        return candidate;
      }
    }
    const firstCandidate = candidates[0];
    if (firstCandidate) return document.querySelector(firstCandidate);
    return null;
  }, []);

  const positionStep = useCallback(() => {
    const tooltipWidth = tooltipRef.current?.offsetWidth || 320;
    const tooltipHeight = tooltipRef.current?.offsetHeight || 200;
    const zoom = getZoom();

    // Welcome step with no target - center tooltip
    if (!step.target) {
      setSpotlight(null);
      setTooltipPos({
        top: window.innerHeight / zoom / 2 - tooltipHeight / 2,
        left: window.innerWidth / zoom / 2 - tooltipWidth / 2,
      });
      return;
    }

    const el = findTargetElement(step.target);
    if (!el) {
      setSpotlight(null);
      setTooltipPos({
        top: window.innerHeight / zoom / 2 - tooltipHeight / 2,
        left: window.innerWidth / zoom / 2 - tooltipWidth / 2,
      });
      return;
    }

    // Scroll element into view if needed
    el.scrollIntoView({ behavior: "smooth", block: "nearest" });

    // Wait for scroll to settle
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        const rect = getSpotlightRect(el!);
        setSpotlight(rect);

        const pos = getTooltipPosition(
          rect,
          step.placement,
          tooltipRef.current
        );
        setTooltipPos(pos);
      });
    });
  }, [findTargetElement, step.placement, step.target]);

  useEffect(() => {
    // Small delay to let the page render
    const timer = setTimeout(() => {
      setIsVisible(true);
      positionStep();
    }, 300);
    return () => clearTimeout(timer);
  }, [positionStep]);

  useEffect(() => {
    if (isVisible) {
      positionStep();
    }
  }, [isVisible, positionStep]);

  // Reposition on resize
  useEffect(() => {
    const handleResize = () => positionStep();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [positionStep]);

  // Reposition after tooltip renders (to get accurate dimensions)
  useEffect(() => {
    if (spotlight && tooltipRef.current) {
      const pos = getTooltipPosition(
        spotlight,
        step.placement,
        tooltipRef.current
      );
      setTooltipPos(pos);
    }
  }, [spotlight, step.placement]);

  const handleNext = () => {
    if (currentStep < TOUR_STEPS.length - 1) {
      setCurrentStep((s) => s + 1);
    } else {
      closeTour(true);
    }
  };

  const handlePrev = () => {
    if (currentStep > 0) {
      setCurrentStep((s) => s - 1);
    }
  };

  const closeTour = (completed: boolean) => {
    setIsExiting(true);
    setTimeout(() => {
      onClose(completed);
    }, 250);
  };

  if (!isVisible) return null;

  const isLastStep = currentStep === TOUR_STEPS.length - 1;

  return (
    <div className={`tour-overlay${isExiting ? " tour-exiting" : ""}`}>
      {/* Dark overlay with spotlight cutout via SVG */}
      <svg className="tour-mask" width="100%" height="100%">
        <defs>
          <mask id="tour-spotlight-mask">
            <rect width="100%" height="100%" fill="white" />
            {spotlight && (
              <rect
                x={spotlight.left}
                y={spotlight.top}
                width={spotlight.width}
                height={spotlight.height}
                rx="8"
                ry="8"
                fill="black"
              />
            )}
          </mask>
        </defs>
        <rect
          width="100%"
          height="100%"
          fill="rgba(20, 25, 18, 0.75)"
          mask="url(#tour-spotlight-mask)"
        />
      </svg>

      {/* Spotlight ring */}
      {spotlight && (
        <div
          className="tour-spotlight-ring"
          style={{
            top: spotlight.top,
            left: spotlight.left,
            width: spotlight.width,
            height: spotlight.height,
          }}
        />
      )}

      {/* Tooltip */}
      {tooltipPos && (
        <div
          ref={tooltipRef}
          className="tour-tooltip"
          style={{ top: tooltipPos.top, left: tooltipPos.left }}
        >
          <button
            className="tour-close"
            onClick={() => closeTour(false)}
            aria-label="Close tour"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>

          <div className="tour-step-indicator">
            {TOUR_STEPS.map((_, i) => (
              <span
                key={i}
                className={`tour-dot${i === currentStep ? " tour-dot-active" : ""}${i < currentStep ? " tour-dot-done" : ""}`}
              />
            ))}
          </div>

          <h3 className="tour-title">{step.title}</h3>
          <p className="tour-content">{step.content}</p>

          <div className="tour-actions">
            {currentStep > 0 && (
              <button className="tour-btn tour-btn-back" onClick={handlePrev}>
                Back
              </button>
            )}
            <button className="tour-btn tour-btn-next" onClick={handleNext}>
              {isLastStep ? "Done" : "Next"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
