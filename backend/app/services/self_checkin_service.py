"""
Resident self check-in: the resident scans the gate, not the other way round.

The existing gate flow has a guard scanning a resident's card. That one keeps
working and is still the fallback for anyone without a phone. This is the
reverse direction, and it is a different security problem entirely.

When a guard scans, the person creating the record is a trusted employee
standing at the gate, and the only question is "who is this". When a resident
scans, the person creating the record is the one who benefits from it being
wrong, and there are two questions: "did you really scan our gate" and "were you
really there". The gate QR answers the first. The geofence answers the second.

Neither is sufficient alone, which is the whole reason both are required:

  - The gate QR is printed on a wall. Anyone can photograph it and send it to a
    friend, so on its own it proves nothing about location.
  - GPS coordinates come from the phone, and a mock-location app can put a phone
    anywhere. So on its own it proves nothing about presence at the gate.

Together they are meaningfully harder: an absent resident needs a photograph of
a code they can only get by being there once, plus a spoofing app, plus a
willingness to leave a false position in an append-only log that staff can read.
That is not proof, and this module does not pretend it is - it is a deterrent
proportionate to a hostel attendance register. Every scan, accepted or refused,
records the position it was given, so the log is reviewable after the fact.

The honest ceiling: this stops casual cheating between friends. It does not stop
a determined resident with a rooted phone. Where attendance carries real
consequences, the guard-scans-resident flow or a biometric device is the
answer, and both remain available alongside this one.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Attendance, Branch, Customer, GateLog, OrganizationSettings
from app.models.enums import (
    AttendanceStatus, AttendanceSubject, CustomerStatus, GateDirection,
)
from app.utils import qr_payload
from app.utils.geo import haversine_metres, is_valid_coordinate

#: A phone that reports its position to worse than this is not being asked to
#: prove anything - indoors on a cold start it will happily claim 1,500 metres,
#: and accepting that reading would make a 150 metre fence meaningless. Refusing
#: is also actionable in a way that a silent pass is not: "step outside" is
#: advice a resident can follow.
MAX_ACCURACY_M = 100.0

#: Source values written to gate_logs / attendance, so the two entry paths stay
#: distinguishable in reports forever. "qr" is a guard scanning a resident.
SOURCE_SELF = "self"


class SelfCheckInError(Exception):
    """
    A refusal the resident should see, with a machine-readable code.

    Raised rather than returned because - unlike the guard's screen, which needs
    to show *who* was refused and therefore always answers 200 - the resident
    already knows who they are. There is nothing to display alongside a refusal,
    so the ordinary error envelope is the right shape.
    """

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class SelfCheckInService:
    """
    Constructed from a resident principal, never from a staff scope.

    There is no `organization_id` parameter anywhere in this class: it is read
    from the authenticated resident row and used to scope every lookup, which is
    the same rule the staff side follows through `CurrentScope`.
    """

    def __init__(self, db: Session, resident: Customer):
        self.db = db
        self.me = resident

    # ------------------------------------------------------------- internals
    def _settings(self) -> OrganizationSettings:
        row = self.db.scalars(select(OrganizationSettings).where(
            OrganizationSettings.organization_id == self.me.organization_id)).first()
        if row is None:
            row = OrganizationSettings(organization_id=self.me.organization_id)
            self.db.add(row)
            self.db.flush()
        return row

    def _my_branch(self) -> Branch | None:
        if self.me.branch_id is None:
            return None
        # Scoped by organisation as well as id. The resident's own branch_id is
        # trustworthy, but reading it through the tenant filter keeps this query
        # the same shape as every other one in the codebase, so it cannot become
        # the exception someone copies later.
        return self.db.scalars(select(Branch).where(
            Branch.id == self.me.branch_id,
            Branch.organization_id == self.me.organization_id)).first()

    def _last_movement(self, now: datetime | None = None) -> GateLog | None:
        """
        The most recent movement that has actually happened.

        Future-dated rows are excluded. `occurred_at` is always server time on
        the write path, so in production this can only be an imported or seeded
        row - but when one exists it sorts to the top of a plain
        `ORDER BY occurred_at DESC` and becomes "the last movement" for good.
        Two things then break at once: direction inference alternates from a
        movement that has not occurred, and the duplicate window compares
        against it instead of the row just written, so double taps stop being
        caught. Both are silent. Excluding them is cheaper than explaining
        either later.
        """
        moment = now or datetime.now(timezone.utc)
        return self.db.scalars(
            select(GateLog).where(GateLog.resident_id == self.me.id,
                                  GateLog.allowed.is_(True),
                                  GateLog.occurred_at <= moment)
            .order_by(GateLog.occurred_at.desc()).limit(1)).first()

    def _log(self, *, branch_id, direction, allowed, now, latitude=None,
             longitude=None, accuracy=None, distance=None, reason=None,
             gate_label=None) -> None:
        self.db.add(GateLog(
            organization_id=self.me.organization_id, branch_id=branch_id,
            resident_id=self.me.id, direction=direction, occurred_at=now,
            gate=gate_label, source=SOURCE_SELF, allowed=allowed, reason=reason,
            latitude=latitude, longitude=longitude,
            accuracy_m=accuracy, distance_m=distance,
            # No `recorded_by_id`: no member of staff was involved. A log row
            # with source="self" and no recorder is exactly what happened, and
            # is more honest than attributing it to whoever owns the branch.
            recorded_by_id=None))
        # Flushed here rather than left pending. Every other write in this class
        # is followed by more work that would flush it anyway, but a refusal
        # raises immediately afterwards - so without this the one row that most
        # needs to survive is the only one whose existence depends on the caller
        # remembering to commit.
        self.db.flush()

    # ---------------------------------------------------------------- status
    def status(self, latitude: float | None, longitude: float | None,
               accuracy: float | None = None) -> dict:
        """
        What the resident's phone should show before they press anything.

        Deliberately answers even when the position is missing or the feature is
        off, because the screen has to explain *why* the button is unavailable.
        A disabled button with no reason is the most common support call there
        is.

        This is advisory only. Everything it reports is checked again inside
        `scan()` against a position sent with the scan itself, so a client that
        lies to this endpoint gains nothing.
        """
        branch = self._my_branch()
        last = self._last_movement()

        payload = {
            "branch_name": branch.name if branch else None,
            "self_checkin_enabled": bool(branch and branch.self_checkin_enabled),
            "geofence_set": bool(branch and branch.has_geofence()),
            "radius_m": branch.geofence_radius_m if branch else None,
            "distance_m": None,
            "accuracy_m": accuracy,
            "in_range": False,
            "next_direction": GateDirection.ENTRY,
            "last_movement": None,
            "reason": None,
        }

        if last is not None:
            payload["last_movement"] = {
                "direction": last.direction,
                "occurred_at": last.occurred_at.isoformat(),
                "source": last.source,
            }
            if last.direction == GateDirection.ENTRY:
                payload["next_direction"] = GateDirection.EXIT

        if branch is None:
            payload["reason"] = "You are not assigned to a branch yet."
            return payload
        if not branch.self_checkin_enabled:
            payload["reason"] = "Self check-in is switched off for this branch."
            return payload
        if not branch.has_geofence():
            payload["reason"] = "This branch has not been positioned on the map yet."
            return payload
        if not is_valid_coordinate(latitude, longitude):
            payload["reason"] = "Waiting for your location."
            return payload

        distance = haversine_metres(latitude, longitude, branch.latitude, branch.longitude)
        payload["distance_m"] = round(distance, 1)

        if accuracy is not None and accuracy > MAX_ACCURACY_M:
            payload["reason"] = (
                f"Your GPS is only accurate to about {int(accuracy)} m. "
                "Step outside or into the open and wait a moment.")
            return payload

        if distance > branch.geofence_radius_m:
            payload["reason"] = (
                f"You are about {int(distance)} m away. Come within "
                f"{branch.geofence_radius_m} m of the gate.")
            return payload

        payload["in_range"] = True
        return payload

    # ------------------------------------------------------------------ scan
    def scan(self, raw_token: str, *, latitude: float | None,
             longitude: float | None, accuracy: float | None = None) -> dict:
        """
        Record an entry or exit from the resident's own phone.

        Order matters here. The checks that reveal nothing run first, and the
        gate token is resolved before the geofence so that a resident standing
        in the right place with the wrong code is told the code is wrong rather
        than being sent walking. The one thing that never happens is a refusal
        that goes unlogged.
        """
        now = datetime.now(timezone.utc)

        # 1. Am I allowed to be here at all? Checked before the token so a
        #    checked-out resident cannot use this endpoint to probe which QR
        #    codes are live.
        if self.me.status == CustomerStatus.CHECKED_OUT:
            raise SelfCheckInError("checked_out", "You have checked out of this PG.")
        if self.me.status not in (CustomerStatus.ACTIVE, CustomerStatus.NOTICE):
            raise SelfCheckInError("inactive", "Your stay is not active.")

        branch = self._my_branch()
        if branch is None:
            raise SelfCheckInError("no_branch", "You are not assigned to a branch yet.")
        if not branch.self_checkin_enabled:
            raise SelfCheckInError(
                "disabled", "Self check-in is switched off for this branch. "
                            "Please use the gate desk.")
        if not branch.has_geofence():
            raise SelfCheckInError(
                "no_geofence", "This branch has not been positioned yet. "
                               "Ask the office to set the gate location.")

        # 2. Is this one of our gates, and is it mine?
        kind, token = qr_payload.parse(raw_token)
        if not token:
            raise SelfCheckInError("invalid", "That code could not be read.")
        if kind == qr_payload.KIND_RESIDENT:
            # Someone pointed the app at another resident's card. Worth its own
            # message: it is a genuine and easy mistake, and "not recognised"
            # would send them looking for a fault that does not exist.
            raise SelfCheckInError(
                "wrong_code", "That is a resident card, not a gate code. "
                              "Scan the code displayed at the gate.")

        scanned = self.db.scalars(select(Branch).where(
            Branch.gate_qr_token == token,
            Branch.organization_id == self.me.organization_id)).first()
        if scanned is None:
            raise SelfCheckInError("invalid", "That is not a gate code we recognise.")
        if scanned.id != branch.id:
            # A real branch, but not this resident's. Named, because the resident
            # is entitled to know they are at the wrong building - and the branch
            # is inside their own organisation, so naming it discloses nothing
            # across a tenant boundary.
            raise SelfCheckInError(
                "wrong_branch", f"That is the gate code for {scanned.name}. "
                                f"You are registered at {branch.name}.")

        # 3. Were you there? Refusals from here on are logged, because a stream
        #    of out-of-range attempts is precisely what staff would want to see.
        if not is_valid_coordinate(latitude, longitude):
            raise SelfCheckInError(
                "no_location", "We could not read your location. Turn on GPS "
                               "and allow location access, then try again.")

        if accuracy is not None and accuracy > MAX_ACCURACY_M:
            raise SelfCheckInError(
                "weak_gps", f"Your GPS is only accurate to about {int(accuracy)} m, "
                            "which is not precise enough. Step into the open and "
                            "wait a few seconds.")

        distance = haversine_metres(latitude, longitude, branch.latitude, branch.longitude)
        if distance > branch.geofence_radius_m:
            self._log(branch_id=branch.id, direction=GateDirection.ENTRY,
                      allowed=False, now=now, latitude=latitude, longitude=longitude,
                      accuracy=accuracy, distance=distance,
                      reason=f"outside geofence ({int(distance)}m)",
                      gate_label=branch.name)
            raise SelfCheckInError(
                "out_of_range",
                f"You are about {int(distance)} m from the gate, and check-in "
                f"works within {branch.geofence_radius_m} m.")

        # 4. Double tap. Held under a row lock on the resident so two taps that
        #    arrive together cannot both read "nothing recent" and both write;
        #    the window check alone is a read-then-write race, and a phone with
        #    a flaky connection retries on its own.
        self.db.scalars(
            select(Customer).where(Customer.id == self.me.id).with_for_update()).first()

        settings = self._settings()
        last = self._last_movement(now)
        # Compared as an absolute gap, not a signed one. A log row dated in the
        # future - a device whose clock ran ahead, an imported record, a badly
        # seeded row - makes `now - last` negative, and a negative number is
        # less than any window. Signed, that reads as "scanned a moment ago" and
        # keeps reading that way forever: the resident is locked out of the gate
        # permanently by a timestamp nobody can see. Absolute value both keeps
        # the double-tap guard under small clock skew and lets a far-future row
        # fall outside the window the way any stale one would.
        gap = abs((now - last.occurred_at).total_seconds()) if last else None
        if last and gap < settings.gate_duplicate_window_seconds:
            seconds = int(gap)
            return {
                "result": "duplicate", "allowed": False, "direction": last.direction,
                "distance_m": round(distance, 1), "branch_name": branch.name,
                "occurred_at": last.occurred_at.isoformat(),
                "message": f"Already recorded {seconds}s ago.",
            }

        # 5. Which way? Same inference the guard's screen uses: alternate from
        #    the last accepted movement, so nobody has to press a mode button.
        direction = (GateDirection.EXIT
                     if last and last.direction == GateDirection.ENTRY
                     else GateDirection.ENTRY)

        self._log(branch_id=branch.id, direction=direction, allowed=True, now=now,
                  latitude=latitude, longitude=longitude, accuracy=accuracy,
                  distance=distance, gate_label=branch.name)

        if direction == GateDirection.ENTRY:
            self._mark_present(now)
        else:
            existing = self.db.scalars(select(Attendance).where(
                Attendance.resident_id == self.me.id,
                Attendance.on_date == now.date())).first()
            if existing:
                existing.check_out_at = now

        return {
            "result": "ok", "allowed": True, "direction": direction,
            "branch_name": branch.name, "distance_m": round(distance, 1),
            "occurred_at": now.isoformat(),
            "message": ("Entry recorded. You are marked present for today."
                        if direction == GateDirection.ENTRY else "Exit recorded."),
        }

    def _mark_present(self, now: datetime) -> None:
        """Upsert by (resident, day), matching the guard-scan path exactly."""
        today: date = now.date()
        row = self.db.scalars(select(Attendance).where(
            Attendance.resident_id == self.me.id,
            Attendance.on_date == today)).first()
        if row is None:
            row = Attendance(
                organization_id=self.me.organization_id, branch_id=self.me.branch_id,
                on_date=today, subject=AttendanceSubject.RESIDENT,
                resident_id=self.me.id)
            self.db.add(row)
        row.status = AttendanceStatus.PRESENT
        row.source = SOURCE_SELF
        if row.check_in_at is None:
            row.check_in_at = now
        self.db.flush()
