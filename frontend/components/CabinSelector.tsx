import type { CabinType, Cabin } from "../types";

interface CabinSelectorProps {
  selectedCabins: CabinType[];
  onChange: (cabins: CabinType[]) => void;
  availability: Record<string, boolean>;
  cabins: Cabin[];
}

export function CabinSelector({ selectedCabins, onChange, availability, cabins }: CabinSelectorProps) {
  return (
    <div className="cabin-selector">
      {cabins.map((cabin) => {
        const isAvailable = availability[cabin.cabin_id] ?? true;
        return (
          <label key={cabin.cabin_id} className="cabin-option">
            <input
              type="radio"
              name="cabin"
              checked={selectedCabins.includes(cabin.cabin_id as CabinType)}
              onChange={() => onChange([cabin.cabin_id as CabinType])}
              disabled={!isAvailable}
            />
            <span className={`cabin-label ${cabin.cabin_id} ${!isAvailable ? "unavailable" : ""}`}>
              {cabin.cabin_name}
              {!isAvailable && <span className="unavailable-text"> (booked)</span>}
            </span>
          </label>
        );
      })}
    </div>
  );
}
