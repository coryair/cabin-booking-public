"""
Multi-agent reservation round simulation using real backend API calls.

Runs the 2026 prime-season priority rounds with one authenticated client per
shareholder, using the time-travel API to place each agent into its booking
window before submitting reservation requests.

Usage:
    cd backend && source venv/bin/activate
    SEED_PASSWORD=<password> SU_PASSWORD=<password> python tests/multi_agent_reservation_rounds_api.py --cleanup
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import date

import httpx

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")
SEED_PASSWORD = os.environ.get("SEED_PASSWORD", "")
SU_PASSWORD = os.environ.get("SU_PASSWORD", SEED_PASSWORD)
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@example.com")


@dataclass(frozen=True)
class Family:
    share_id: str
    name: str
    email: str
    priority: int


@dataclass(frozen=True)
class ReservationRequest:
    start_date: str
    end_date: str
    cabin: str


@dataclass(frozen=True)
class RoundConfig:
    key: str
    label: str
    order: list[str]
    windows: dict[str, tuple[str, str]]


FAMILIES = [
    Family("alder", "Alder", "alder@example.com", 1),
    Family("birch", "Birch", "birch@example.com", 2),
    Family("aspen", "Aspen", "aspen@example.com", 3),
    Family("maple", "Demo Four", "maple@example.com", 4),
    Family("oak", "Oak", "oak@example.com", 5),
    Family("willow", "Demo Six", "willow@example.com", 6),
    Family("spruce", "Spruce", "spruce@example.com", 7),
    Family("elm", "Demo Eight", "elm@example.com", 8),
    Family("fir", "Fir", "fir@example.com", 9),
]

FAMILY_BY_ID = {f.share_id: f for f in FAMILIES}
MISSED_WINDOWS: dict[str, set[str]] = {
    "willow": {"round_1"},
}

REQUESTS_BY_ROUND: dict[str, dict[str, list[ReservationRequest]]] = {
    "round_1": {
        "alder": [
            ReservationRequest("2026-06-05", "2026-06-09", "pine"),
            ReservationRequest("2026-07-10", "2026-07-13", "cedar"),
        ],
        "birch": [
            ReservationRequest("2026-06-05", "2026-06-09", "pine"),
            ReservationRequest("2026-06-09", "2026-06-12", "pine"),
        ],
        "aspen": [
            ReservationRequest("2026-06-09", "2026-06-12", "pine"),
            ReservationRequest("2026-06-12", "2026-06-15", "cedar"),
        ],
        "maple": [
            ReservationRequest("2026-06-14", "2026-06-18", "pine"),
        ],
        "oak": [
            ReservationRequest("2026-07-04", "2026-07-08", "pine"),
        ],
        "spruce": [
            ReservationRequest("2026-07-10", "2026-07-13", "cedar"),
            ReservationRequest("2026-07-13", "2026-07-16", "cedar"),
        ],
        "elm": [
            ReservationRequest("2026-07-04", "2026-07-08", "pine"),
            ReservationRequest("2026-07-16", "2026-07-19", "pine"),
        ],
        "fir": [
            ReservationRequest("2026-08-01", "2026-08-05", "cedar"),
        ],
    },
    "round_2": {
        "fir": [ReservationRequest("2026-08-10", "2026-08-24", "pine")],
        "elm": [
            ReservationRequest("2026-08-12", "2026-08-16", "pine"),
            ReservationRequest("2026-08-14", "2026-08-18", "cedar"),
        ],
        "spruce": [
            ReservationRequest("2026-08-14", "2026-08-18", "cedar"),
            ReservationRequest("2026-08-18", "2026-08-22", "cedar"),
        ],
        "willow": [
            ReservationRequest("2026-08-18", "2026-08-22", "cedar"),
            ReservationRequest("2026-08-22", "2026-08-26", "cedar"),
        ],
        "oak": [
            ReservationRequest("2026-08-22", "2026-08-26", "cedar"),
            ReservationRequest("2026-08-26", "2026-08-30", "pine"),
        ],
        "maple": [
            ReservationRequest("2026-08-26", "2026-08-30", "pine"),
            ReservationRequest("2026-08-30", "2026-09-02", "cedar"),
        ],
        "aspen": [
            ReservationRequest("2026-08-30", "2026-09-02", "cedar"),
            ReservationRequest("2026-09-02", "2026-09-05", "pine"),
        ],
        "birch": [
            ReservationRequest("2026-09-02", "2026-09-05", "pine"),
            ReservationRequest("2026-09-05", "2026-09-08", "cedar"),
        ],
        "alder": [
            ReservationRequest("2026-09-05", "2026-09-08", "cedar"),
            ReservationRequest("2026-08-06", "2026-08-09", "pine"),
        ],
    },
    "round_3": {
        "alder": [ReservationRequest("2026-05-25", "2026-05-28", "pine")],
        "birch": [
            ReservationRequest("2026-05-25", "2026-05-28", "pine"),
            ReservationRequest("2026-05-28", "2026-05-31", "pine"),
        ],
        "aspen": [
            ReservationRequest("2026-05-28", "2026-05-31", "pine"),
            ReservationRequest("2026-05-31", "2026-06-03", "cedar"),
        ],
        "maple": [
            ReservationRequest("2026-05-31", "2026-06-03", "cedar"),
            ReservationRequest("2026-06-03", "2026-06-06", "cedar"),
        ],
        "oak": [
            ReservationRequest("2026-06-03", "2026-06-06", "cedar"),
            ReservationRequest("2026-06-06", "2026-06-09", "cedar"),
        ],
        "willow": [
            ReservationRequest("2026-06-06", "2026-06-09", "cedar"),
            ReservationRequest("2026-06-09", "2026-06-12", "cedar"),
        ],
        "spruce": [
            ReservationRequest("2026-06-09", "2026-06-12", "cedar"),
            ReservationRequest("2026-06-15", "2026-06-18", "pine"),
            ReservationRequest("2026-06-18", "2026-06-21", "pine"),
        ],
        "elm": [
            ReservationRequest("2026-06-18", "2026-06-21", "pine"),
            ReservationRequest("2026-06-21", "2026-06-24", "pine"),
        ],
        "fir": [
            ReservationRequest("2026-06-21", "2026-06-24", "pine"),
            ReservationRequest("2026-06-24", "2026-06-27", "pine"),
        ],
    },
}

ROUND_1_WINDOWS = {
    "alder": ("2026-04-01", "2026-04-02"),
    "birch": ("2026-04-03", "2026-04-04"),
    "aspen": ("2026-04-05", "2026-04-06"),
    "maple": ("2026-04-07", "2026-04-08"),
    "oak": ("2026-04-09", "2026-04-10"),
    "willow": ("2026-04-11", "2026-04-12"),
    "spruce": ("2026-04-13", "2026-04-14"),
    "elm": ("2026-04-15", "2026-04-16"),
    "fir": ("2026-04-17", "2026-04-18"),
}

ROUND_2_WINDOWS = {
    "fir": ("2026-04-20", "2026-04-21"),
    "elm": ("2026-04-22", "2026-04-23"),
    "spruce": ("2026-04-24", "2026-04-25"),
    "willow": ("2026-04-26", "2026-04-27"),
    "oak": ("2026-04-28", "2026-04-29"),
    "maple": ("2026-04-30", "2026-05-01"),
    "aspen": ("2026-05-02", "2026-05-03"),
    "birch": ("2026-05-04", "2026-05-05"),
    "alder": ("2026-05-06", "2026-05-07"),
}

ROUND_3_WINDOWS = {
    "alder": ("2026-05-10", "2026-05-10"),
    "birch": ("2026-05-11", "2026-05-11"),
    "aspen": ("2026-05-12", "2026-05-12"),
    "maple": ("2026-05-13", "2026-05-13"),
    "oak": ("2026-05-14", "2026-05-14"),
    "willow": ("2026-05-15", "2026-05-15"),
    "spruce": ("2026-05-16", "2026-05-16"),
    "elm": ("2026-05-17", "2026-05-17"),
    "fir": ("2026-05-18", "2026-05-18"),
}

ROUNDS = [
    RoundConfig(
        key="round_1",
        label="ROUND 1 (priority order)",
        order=[f.share_id for f in FAMILIES],
        windows=ROUND_1_WINDOWS,
    ),
    RoundConfig(
        key="round_2",
        label="ROUND 2 (reverse priority)",
        order=list(reversed([f.share_id for f in FAMILIES])),
        windows=ROUND_2_WINDOWS,
    ),
    RoundConfig(
        key="round_3",
        label="ROUND 3 (priority order, <18 nights only by policy)",
        order=[f.share_id for f in FAMILIES],
        windows=ROUND_3_WINDOWS,
    ),
]


def nights(start_date: str, end_date: str) -> int:
    return (date.fromisoformat(end_date) - date.fromisoformat(start_date)).days


def login(email: str, password: str) -> httpx.Client:
    client = httpx.Client(base_url=BASE_URL)
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    if resp.status_code != 200:
        raise RuntimeError(f"Login failed for {email}: {resp.status_code} {resp.text}")
    return client


def check_backend() -> None:
    try:
        resp = httpx.get(f"{BASE_URL}/health", timeout=5)
    except Exception as exc:
        raise RuntimeError(f"Cannot connect to backend at {BASE_URL}: {exc}") from exc
    if resp.status_code != 200:
        raise RuntimeError(f"Backend health check failed: {resp.status_code} {resp.text}")


def set_date(admin: httpx.Client, date_str: str) -> None:
    resp = admin.post("/api/time-travel", json={"date": date_str})
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to set time-travel date {date_str}: {resp.status_code} {resp.text}")


def clear_date(admin: httpx.Client) -> None:
    resp = admin.delete("/api/time-travel")
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to clear time travel: {resp.status_code} {resp.text}")


def cleanup_reservations(admin: httpx.Client) -> int:
    resp = admin.get("/api/reservations")
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to list reservations for cleanup: {resp.status_code} {resp.text}")
    existing = resp.json()
    for item in existing:
        reservation_id = item["id"]
        del_resp = admin.delete(f"/api/reservations/{reservation_id}")
        if del_resp.status_code != 200:
            raise RuntimeError(
                f"Failed deleting reservation {reservation_id}: {del_resp.status_code} {del_resp.text}"
            )
    return len(existing)


def get_booking_status(client: httpx.Client) -> dict:
    resp = client.get("/api/booking-status")
    if resp.status_code != 200:
        raise RuntimeError(f"Failed getting booking status: {resp.status_code} {resp.text}")
    return resp.json()


def create_reservation(client: httpx.Client, req: ReservationRequest) -> httpx.Response:
    payload = {
        "share": "",
        "guest_count": 0,
        "start_date": req.start_date,
        "end_date": req.end_date,
        "cabins": [req.cabin],
        "is_day_use": False,
    }
    return client.post("/api/reservations", json=payload)


def print_round_header(label: str) -> None:
    print(f"\n{'=' * 72}")
    print(label)
    print(f"{'=' * 72}")


def run_simulation(cleanup: bool) -> int:
    if not SEED_PASSWORD:
        print("ERROR: SEED_PASSWORD must be set.")
        return 1
    if not SU_PASSWORD:
        print("ERROR: SU_PASSWORD must be set (or SEED_PASSWORD must also work for admin).")
        return 1

    check_backend()

    admin = login(ADMIN_EMAIL, SU_PASSWORD)
    clients: dict[str, httpx.Client] = {}
    accepted = 0
    rejected = 0
    errored = 0
    accepted_nights: dict[str, int] = {f.share_id: 0 for f in FAMILIES}

    try:
        for family in FAMILIES:
            clients[family.share_id] = login(family.email, SEED_PASSWORD)

        if cleanup:
            removed = cleanup_reservations(admin)
            print(f"Cleanup complete: removed {removed} existing reservations.")

        for round_cfg in ROUNDS:
            print_round_header(round_cfg.label)
            for share_id in round_cfg.order:
                family = FAMILY_BY_ID[share_id]
                window_start, window_end = round_cfg.windows[share_id]
                set_date(admin, window_start)
                status = get_booking_status(clients[share_id])

                print(
                    f"\n{family.name} (priority {family.priority}) window {window_start} -> {window_end} | "
                    f"current_round={status.get('current_round')} can_book={status.get('can_book')}"
                )

                if round_cfg.key in MISSED_WINDOWS.get(share_id, set()):
                    print("  SKIP: configured as missed window (forfeit).")
                    continue

                requests = REQUESTS_BY_ROUND.get(round_cfg.key, {}).get(share_id, [])
                if not requests:
                    print("  SKIP: no request configured.")
                    continue

                for req in requests:
                    resp = create_reservation(clients[share_id], req)
                    label = f"{req.start_date}->{req.end_date} {req.cabin}"
                    if resp.status_code == 200:
                        body = resp.json()
                        booking_round = body.get("booking_round")
                        accepted += 1
                        accepted_nights[share_id] += nights(req.start_date, req.end_date)
                        print(f"  ACCEPT {label} id={body.get('id')} booking_round={booking_round}")
                    elif resp.status_code == 400:
                        rejected += 1
                        detail = resp.json().get("detail", "")
                        print(f"  REJECT {label} reason={detail}")
                    else:
                        errored += 1
                        print(f"  ERROR  {label} status={resp.status_code} body={resp.text}")

        print("\nSummary:")
        print(f"- accepted: {accepted}")
        print(f"- rejected (policy/conflict): {rejected}")
        print(f"- unexpected errors: {errored}")
        for family in FAMILIES:
            share_nights = accepted_nights[family.share_id]
            print(f"- {family.name:14} accepted_nights={share_nights}")

        return 1 if errored else 0
    finally:
        try:
            clear_date(admin)
        except Exception as exc:
            print(f"WARNING: failed to clear time travel: {exc}")
        admin.close()
        for client in clients.values():
            client.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run real-API multi-agent reservation round simulation.")
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Delete all existing reservations before simulation starts.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    code = run_simulation(cleanup=args.cleanup)
    sys.exit(code)


if __name__ == "__main__":
    main()
