import { useRef, useEffect, useState, type CSSProperties, type MouseEvent as ReactMouseEvent, type ReactNode } from "react";
import { getZoom } from "../utils";

interface TooltipProps {
  text: string;
  position?: "top" | "bottom";
  children: ReactNode;
}

export function Tooltip({ text, position = "top", children }: TooltipProps) {
  const [style, setStyle] = useState<CSSProperties>({});
  const [visible, setVisible] = useState(false);
  const wrapperRef = useRef<HTMLSpanElement>(null);
  const bubbleRef = useRef<HTMLDivElement>(null);

  const updatePosition = () => {
    requestAnimationFrame(() => {
      const wrapper = wrapperRef.current;
      const bubble = bubbleRef.current;
      if (!wrapper || !bubble) return;

      const rawRect = wrapper.getBoundingClientRect();
      const zoom = getZoom();
      const wr = {
        top: rawRect.top / zoom,
        left: rawRect.left / zoom,
        bottom: rawRect.bottom / zoom,
        width: rawRect.width / zoom,
      };
      const bw = bubble.offsetWidth;
      const bh = bubble.offsetHeight;
      const pad = 8;
      const gap = 6;
      const vw = window.innerWidth / zoom;
      const vh = window.innerHeight / zoom;

      // Vertical: prefer requested position, flip if no room
      let useTop = position === "top";
      if (useTop && wr.top - bh - gap < 0) useTop = false;
      else if (!useTop && wr.bottom + bh + gap > vh) useTop = true;

      const top = useTop ? wr.top - bh - gap : wr.bottom + gap;

      // Horizontal: center on wrapper, clamp to viewport
      let left = wr.left + wr.width / 2 - bw / 2;
      if (left + bw > vw - pad) left = vw - pad - bw;
      if (left < pad) left = pad;

      setStyle({ top, left, position: "fixed" });
    });
  };

  const showTooltip = () => {
    setVisible(true);
    updatePosition();
  };

  const handleMouseEnter = () => {
    showTooltip();
  };

  const handleMouseLeave = () => {
    setVisible(false);
  };

  const handleClick = (event: ReactMouseEvent<HTMLSpanElement>) => {
    event.stopPropagation();
    setVisible((current) => {
      const nextVisible = !current;
      if (nextVisible) {
        updatePosition();
      }
      return nextVisible;
    });
  };

  useEffect(() => {
    if (!visible) return;

    const handleDocumentClick = (event: globalThis.MouseEvent) => {
      const target = event.target as Node | null;
      if (!target) return;
      if (!wrapperRef.current?.contains(target)) {
        setVisible(false);
      }
    };

    document.addEventListener("click", handleDocumentClick);
    return () => {
      document.removeEventListener("click", handleDocumentClick);
    };
  }, [visible]);

  return (
    <span
      ref={wrapperRef}
      className="tooltip-wrapper"
      onClick={handleClick}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      {children}
      <div
        ref={bubbleRef}
        className={`tooltip-bubble${visible ? " tooltip-visible" : ""}`}
        role="tooltip"
        style={style}
      >
        {text}
      </div>
    </span>
  );
}

interface InfoTipProps {
  text: string;
}

export function InfoTip({ text }: InfoTipProps) {
  return (
    <Tooltip text={text}>
      <span className="info-icon" aria-label="More info">i</span>
    </Tooltip>
  );
}
