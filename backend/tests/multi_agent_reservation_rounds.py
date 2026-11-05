"""
Multi-agent simulation of the Cabin Booking 2026 prime-season reservation rounds.

This is a policy simulator (no API calls) that models one autonomous agent per
shareholder and executes Round 1 -> Round 2 -> Round 3 rules from the
"CABINS 2026 RESERVATION PROCESS" document.

Usage:
    python3 backend/tests/multi_agent_reservation_rounds.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


def d(value: str) -> date:
    return date.fromisoformat(value)


def nights(start: date, end: date) -> int:
    return (end - start).days


def overlaps(start_a: date, end_a: date, start_b: date, end_b: date) -> bool:
    return start_a < end_b and end_a > start_b


@dataclass(frozen=True)
class ReservationRequest:
    start: date
    end: date
    cabin: str
    payment_success: bool = True


@dataclass
class Reservation:
    share_id: str
    share_name: str
    start: date
    end: date
    cabin: str
    booking_round: str


@dataclass
class Agent:
    share_id: str
    name: str
    priority: int
    assessment_paid: bool = True
    missed_rounds: set[str] = field(default_factory=set)
    requests_by_round: dict[str, list[ReservationRequest]] = field(default_factory=dict)


@dataclass(frozen=True)
class RoundConfig:
    key: str
    label: str
    order: list[str]
    windows: dict[str, tuple[str, str]]
    max_reservations: int
    max_round_nights: int | None
    require_total_nights_below_cap: bool = False


class RoundSimulator:
    SEASON_MAX_NIGHTS = 18
    PRIME_START = d("2026-05-22")
    PRIME_END = d("2026-09-08")
    CABINS = {"pine", "cedar"}

    def __init__(self, agents: list[Agent]):
        self.agents = {a.share_id: a for a in agents}
        self.reservations: list[Reservation] = []
        self.logs: list[str] = []
        self.total_nights_by_share = {a.share_id: 0 for a in agents}

    def _round_reservations(self, share_id: str, round_key: str) -> list[Reservation]:
        return [
            r for r in self.reservations
            if r.share_id == share_id and r.booking_round == round_key
        ]

    def _round_nights(self, share_id: str, round_key: str) -> int:
        return sum(nights(r.start, r.end) for r in self._round_reservations(share_id, round_key))

    def _find_conflict(self, req: ReservationRequest) -> Reservation | None:
        for existing in self.reservations:
            if existing.cabin != req.cabin:
                continue
            if overlaps(req.start, req.end, existing.start, existing.end):
                return existing
        return None

    def _try_book(self, agent: Agent, round_cfg: RoundConfig, req: ReservationRequest) -> bool:
        req_nights = nights(req.start, req.end)
        round_bookings = self._round_reservations(agent.share_id, round_cfg.key)
        round_nights = self._round_nights(agent.share_id, round_cfg.key)
        total_nights = self.total_nights_by_share[agent.share_id]

        if req.cabin not in self.CABINS:
            self.logs.append(
                f"  REJECT {agent.name}: invalid cabin '{req.cabin}'"
            )
            return False

        if req.end <= req.start:
            self.logs.append(
                f"  REJECT {agent.name}: invalid date range {req.start} -> {req.end}"
            )
            return False

        if req.start < self.PRIME_START or req.end > self.PRIME_END:
            self.logs.append(
                f"  REJECT {agent.name}: {req.start} -> {req.end} outside prime season"
            )
            return False

        if len(round_bookings) >= round_cfg.max_reservations:
            self.logs.append(
                f"  REJECT {agent.name}: round max reservations reached ({round_cfg.max_reservations})"
            )
            return False

        if total_nights + req_nights > self.SEASON_MAX_NIGHTS:
            self.logs.append(
                f"  REJECT {agent.name}: season cap exceeded ({total_nights}+{req_nights} > {self.SEASON_MAX_NIGHTS})"
            )
            return False

        if round_cfg.max_round_nights is not None and (round_nights + req_nights > round_cfg.max_round_nights):
            self.logs.append(
                f"  REJECT {agent.name}: round night cap exceeded ({round_nights}+{req_nights} > {round_cfg.max_round_nights})"
            )
            return False

        if not req.payment_success:
            self.logs.append(
                f"  REJECT {agent.name}: payment failed for {req.start} -> {req.end} {req.cabin}"
            )
            return False

        conflict = self._find_conflict(req)
        if conflict:
            self.logs.append(
                "  REJECT "
                f"{agent.name}: conflict on {req.cabin} {req.start}->{req.end} "
                f"(held by {conflict.share_name} {conflict.start}->{conflict.end}); "
                "priority winner keeps reservation"
            )
            return False

        self.reservations.append(
            Reservation(
                share_id=agent.share_id,
                share_name=agent.name,
                start=req.start,
                end=req.end,
                cabin=req.cabin,
                booking_round=round_cfg.key,
            )
        )
        self.total_nights_by_share[agent.share_id] += req_nights
        new_total = self.total_nights_by_share[agent.share_id]
        self.logs.append(
            f"  ACCEPT {agent.name}: {req.start}->{req.end} {req.cabin} ({req_nights} nights), total={new_total}"
        )
        return True

    def run_round(self, round_cfg: RoundConfig):
        self.logs.append(f"\n=== {round_cfg.label} ===")
        for share_id in round_cfg.order:
            agent = self.agents[share_id]
            window_start, window_end = round_cfg.windows[share_id]
            total_nights = self.total_nights_by_share[share_id]

            self.logs.append(
                f"\n{agent.name} (priority {agent.priority}) window {window_start} -> {window_end}"
            )

            if not agent.assessment_paid:
                self.logs.append("  SKIP: annual assessment unpaid by March 15")
                continue

            if round_cfg.key in agent.missed_rounds:
                self.logs.append("  FORFEIT: missed booking window")
                continue

            if round_cfg.require_total_nights_below_cap and total_nights >= self.SEASON_MAX_NIGHTS:
                self.logs.append(
                    f"  SKIP: not eligible for Round 3 (already at {self.SEASON_MAX_NIGHTS} nights)"
                )
                continue

            requests = agent.requests_by_round.get(round_cfg.key, [])
            if not requests:
                self.logs.append("  SKIP: no requests submitted")
                continue

            for req in requests:
                accepted = self._try_book(agent, round_cfg, req)
                if accepted and len(self._round_reservations(share_id, round_cfg.key)) >= round_cfg.max_reservations:
                    break

    def print_summary(self):
        print("\n=== FINAL SUMMARY ===")
        for share_id, agent in sorted(self.agents.items(), key=lambda item: item[1].priority):
            total = self.total_nights_by_share[share_id]
            r1 = self._round_nights(share_id, "round_1")
            r2 = self._round_nights(share_id, "round_2")
            r3 = self._round_nights(share_id, "round_3")
            print(f"{agent.name:14} total={total:2} nights | R1={r1:2} R2={r2:2} R3={r3:2}")

        print("\nAccepted reservations:")
        for res in sorted(self.reservations, key=lambda r: (r.start, r.cabin, r.share_name)):
            print(
                f"- {res.start} -> {res.end} {res.cabin:7} {res.share_name:14} ({res.booking_round})"
            )


def build_agents() -> list[Agent]:
    return [
        Agent(
            share_id="alder",
            name="Alder",
            priority=1,
            requests_by_round={
                "round_1": [
                    ReservationRequest(d("2026-06-05"), d("2026-06-09"), "pine"),
                    ReservationRequest(d("2026-07-10"), d("2026-07-13"), "cedar"),
                ],
                "round_2": [
                    ReservationRequest(d("2026-09-05"), d("2026-09-08"), "cedar"),
                    ReservationRequest(d("2026-08-06"), d("2026-08-09"), "pine"),
                ],
                "round_3": [
                    ReservationRequest(d("2026-05-25"), d("2026-05-28"), "pine"),
                ],
            },
        ),
        Agent(
            share_id="birch",
            name="Birch",
            priority=2,
            requests_by_round={
                "round_1": [
                    ReservationRequest(d("2026-06-05"), d("2026-06-09"), "pine"),
                    ReservationRequest(d("2026-06-09"), d("2026-06-12"), "pine"),
                ],
                "round_2": [
                    ReservationRequest(d("2026-09-02"), d("2026-09-05"), "pine"),
                    ReservationRequest(d("2026-09-05"), d("2026-09-08"), "cedar"),
                ],
                "round_3": [
                    ReservationRequest(d("2026-05-25"), d("2026-05-28"), "pine"),
                    ReservationRequest(d("2026-05-28"), d("2026-05-31"), "pine"),
                ],
            },
        ),
        Agent(
            share_id="aspen",
            name="Aspen",
            priority=3,
            requests_by_round={
                "round_1": [
                    ReservationRequest(d("2026-06-09"), d("2026-06-12"), "pine"),
                    ReservationRequest(d("2026-06-12"), d("2026-06-15"), "cedar"),
                ],
                "round_2": [
                    ReservationRequest(d("2026-08-30"), d("2026-09-02"), "cedar"),
                    ReservationRequest(d("2026-09-02"), d("2026-09-05"), "pine"),
                ],
                "round_3": [
                    ReservationRequest(d("2026-05-28"), d("2026-05-31"), "pine"),
                    ReservationRequest(d("2026-05-31"), d("2026-06-03"), "cedar"),
                ],
            },
        ),
        Agent(
            share_id="maple",
            name="Demo Four",
            priority=4,
            requests_by_round={
                "round_1": [
                    ReservationRequest(d("2026-06-14"), d("2026-06-18"), "pine"),
                ],
                "round_2": [
                    ReservationRequest(d("2026-08-26"), d("2026-08-30"), "pine"),
                    ReservationRequest(d("2026-08-30"), d("2026-09-02"), "cedar"),
                ],
                "round_3": [
                    ReservationRequest(d("2026-05-31"), d("2026-06-03"), "cedar"),
                    ReservationRequest(d("2026-06-03"), d("2026-06-06"), "cedar"),
                ],
            },
        ),
        Agent(
            share_id="oak",
            name="Oak",
            priority=5,
            requests_by_round={
                "round_1": [
                    ReservationRequest(d("2026-07-04"), d("2026-07-08"), "pine"),
                ],
                "round_2": [
                    ReservationRequest(d("2026-08-22"), d("2026-08-26"), "cedar"),
                    ReservationRequest(d("2026-08-26"), d("2026-08-30"), "pine"),
                ],
                "round_3": [
                    ReservationRequest(d("2026-06-03"), d("2026-06-06"), "cedar"),
                    ReservationRequest(d("2026-06-06"), d("2026-06-09"), "cedar"),
                ],
            },
        ),
        Agent(
            share_id="willow",
            name="Demo Six",
            priority=6,
            missed_rounds={"round_1"},
            requests_by_round={
                "round_2": [
                    ReservationRequest(d("2026-08-18"), d("2026-08-22"), "cedar"),
                    ReservationRequest(d("2026-08-22"), d("2026-08-26"), "cedar", payment_success=False),
                    ReservationRequest(d("2026-08-22"), d("2026-08-26"), "cedar"),
                ],
                "round_3": [
                    ReservationRequest(d("2026-06-06"), d("2026-06-09"), "cedar"),
                    ReservationRequest(d("2026-06-09"), d("2026-06-12"), "cedar"),
                ],
            },
        ),
        Agent(
            share_id="spruce",
            name="Spruce",
            priority=7,
            requests_by_round={
                "round_1": [
                    ReservationRequest(d("2026-07-10"), d("2026-07-13"), "cedar"),
                    ReservationRequest(d("2026-07-13"), d("2026-07-16"), "cedar"),
                ],
                "round_2": [
                    ReservationRequest(d("2026-08-14"), d("2026-08-18"), "cedar"),
                    ReservationRequest(d("2026-08-18"), d("2026-08-22"), "cedar"),
                ],
                "round_3": [
                    ReservationRequest(d("2026-06-09"), d("2026-06-12"), "cedar"),
                    ReservationRequest(d("2026-06-15"), d("2026-06-18"), "pine"),
                    ReservationRequest(d("2026-06-18"), d("2026-06-21"), "pine"),
                ],
            },
        ),
        Agent(
            share_id="rodman_elm",
            name="Demo Eight",
            priority=8,
            requests_by_round={
                "round_1": [
                    ReservationRequest(d("2026-07-04"), d("2026-07-08"), "pine"),
                    ReservationRequest(d("2026-07-16"), d("2026-07-19"), "pine"),
                ],
                "round_2": [
                    ReservationRequest(d("2026-08-12"), d("2026-08-16"), "pine"),
                    ReservationRequest(d("2026-08-14"), d("2026-08-18"), "cedar"),
                ],
                "round_3": [
                    ReservationRequest(d("2026-06-18"), d("2026-06-21"), "pine"),
                    ReservationRequest(d("2026-06-21"), d("2026-06-24"), "pine"),
                ],
            },
        ),
        Agent(
            share_id="fir",
            name="Fir",
            priority=9,
            requests_by_round={
                "round_1": [
                    ReservationRequest(d("2026-08-01"), d("2026-08-05"), "cedar"),
                ],
                "round_2": [
                    ReservationRequest(d("2026-08-10"), d("2026-08-24"), "pine"),
                ],
                "round_3": [
                    ReservationRequest(d("2026-06-21"), d("2026-06-24"), "pine"),
                    ReservationRequest(d("2026-06-24"), d("2026-06-27"), "pine"),
                ],
            },
        ),
    ]


def round_definitions() -> list[RoundConfig]:
    priority_order = [
        "alder",
        "birch",
        "aspen",
        "maple",
        "oak",
        "willow",
        "spruce",
        "rodman_elm",
        "fir",
    ]
    reverse_order = list(reversed(priority_order))

    round_1_windows = {
        "alder": ("2026-04-01", "2026-04-02"),
        "birch": ("2026-04-03", "2026-04-04"),
        "aspen": ("2026-04-05", "2026-04-06"),
        "maple": ("2026-04-07", "2026-04-08"),
        "oak": ("2026-04-09", "2026-04-10"),
        "willow": ("2026-04-11", "2026-04-12"),
        "spruce": ("2026-04-13", "2026-04-14"),
        "rodman_elm": ("2026-04-15", "2026-04-16"),
        "fir": ("2026-04-17", "2026-04-18"),
    }
    round_2_windows = {
        "fir": ("2026-04-20", "2026-04-21"),
        "rodman_elm": ("2026-04-22", "2026-04-23"),
        "spruce": ("2026-04-24", "2026-04-25"),
        "willow": ("2026-04-26", "2026-04-27"),
        "oak": ("2026-04-28", "2026-04-29"),
        "maple": ("2026-04-30", "2026-05-01"),
        "aspen": ("2026-05-02", "2026-05-03"),
        "birch": ("2026-05-04", "2026-05-05"),
        "alder": ("2026-05-06", "2026-05-07"),
    }
    round_3_windows = {
        "alder": ("2026-05-10", "2026-05-10"),
        "birch": ("2026-05-11", "2026-05-11"),
        "aspen": ("2026-05-12", "2026-05-12"),
        "maple": ("2026-05-13", "2026-05-13"),
        "oak": ("2026-05-14", "2026-05-14"),
        "willow": ("2026-05-15", "2026-05-15"),
        "spruce": ("2026-05-16", "2026-05-16"),
        "rodman_elm": ("2026-05-17", "2026-05-17"),
        "fir": ("2026-05-18", "2026-05-18"),
    }

    return [
        RoundConfig(
            key="round_1",
            label="ROUND 1 (Apr 1-18): priority order, 2 reservations max, 10 nights max",
            order=priority_order,
            windows=round_1_windows,
            max_reservations=2,
            max_round_nights=10,
        ),
        RoundConfig(
            key="round_2",
            label="ROUND 2 (Apr 20-May 7): reverse order, 1 reservation max, 18 season-night cap",
            order=reverse_order,
            windows=round_2_windows,
            max_reservations=1,
            max_round_nights=None,
        ),
        RoundConfig(
            key="round_3",
            label="ROUND 3 (May 10-18): priority order, only shares below 18 nights, 1 reservation max",
            order=priority_order,
            windows=round_3_windows,
            max_reservations=1,
            max_round_nights=None,
            require_total_nights_below_cap=True,
        ),
    ]


def main():
    agents = build_agents()
    simulator = RoundSimulator(agents)

    for round_cfg in round_definitions():
        simulator.run_round(round_cfg)

    for line in simulator.logs:
        print(line)
    simulator.print_summary()


if __name__ == "__main__":
    main()
