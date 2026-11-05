interface TimeTravelBannerProps {
  isActive: boolean;
  simulatedDate: string | null;
}

export function TimeTravelBanner({ isActive, simulatedDate }: TimeTravelBannerProps) {
  if (!isActive || !simulatedDate) return null;

  const formatted = new Date(simulatedDate + "T00:00:00").toLocaleDateString("en-US", {
    weekday: "short",
    month: "long",
    day: "numeric",
    year: "numeric",
  });

  return (
    <div className="time-travel-banner">
      SIMULATION MODE - Today is {formatted}
    </div>
  );
}
