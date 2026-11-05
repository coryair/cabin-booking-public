"""
Analytics role unit checks.

Run:
    python backend/tests/analytics_role_unit_test.py
"""

from pathlib import Path
import sys
from types import SimpleNamespace


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from routers.auth import has_admin_access, has_analytics_access


def role(**overrides):
    defaults = {
        "is_viewer": 0,
        "is_analytics": 0,
        "is_admin": 0,
        "is_superadmin": 0,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def main() -> int:
    analytics = role(is_analytics=1)
    admin = role(is_admin=1)
    superadmin = role(is_superadmin=1)
    viewer = role(is_viewer=1)
    user = role()

    assert has_analytics_access(analytics)
    assert has_analytics_access(admin)
    assert has_analytics_access(superadmin)
    assert not has_analytics_access(viewer)
    assert not has_analytics_access(user)

    assert not has_admin_access(analytics)
    assert has_admin_access(admin)
    assert has_admin_access(superadmin)
    assert not has_admin_access(user)

    print("analytics role checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
