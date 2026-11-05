import { InfoTip } from "./Tooltip";
import type { Cabin } from "../types";

interface CalendarLegendProps {
  cabins: Cabin[];
}

export function CalendarLegend({ cabins }: CalendarLegendProps) {
  const orderedCabins = [...cabins].sort((a, b) => {
    const rank = (id: string) => {
      if (id === "pine") return 0;
      if (id === "cedar") return 1;
      return 2;
    };
    const rankDiff = rank(a.cabin_id) - rank(b.cabin_id);
    if (rankDiff !== 0) return rankDiff;
    return a.cabin_name.localeCompare(b.cabin_name);
  });

  return (
    <div className="calendar-legend" data-tour="calendar-legend">
      {orderedCabins.map((cabin) => (
        <div key={cabin.cabin_id} className="legend-item">
          <span className={`legend-bar ${cabin.cabin_id}`} />
          <span>{cabin.cabin_name}</span>
        </div>
      ))}
      <div className="legend-item">
        <span className="legend-bar legend-bar-dayuse" />
        <span>Day Use</span>
      </div>
      <InfoTip text="Colors show which cabin is reserved" />
    </div>
  );
}
