"""
Resident self check-in: the geofence, the gate code, and the isolation around
both.

The point of this file is that self check-in inverts who creates the record. In
the guard-scan flow the writer is a trusted employee; here the writer is the
person who benefits from the record being wrong. So the tests that matter are
not the happy path - they are the refusals, and the proof that a refusal cannot
be talked out of by editing a request.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Attendance, Customer, GateLog, OrganizationSettings
from app.models.enums import CustomerStatus, GateDirection
from app.services.self_checkin_service import (
    MAX_ACCURACY_M, SelfCheckInError, SelfCheckInService,
)
from app.utils import qr_payload
from app.utils.geo import haversine_metres, is_valid_coordinate
from tests.factories import make_branch, make_customer, make_org

# A real gate, and points a known distance from it. Bengaluru, because the
# numbers below were checked against a map and a wrong constant here would
# quietly weaken every geofence test in the file.
GATE_LAT, GATE_LNG = 12.934533, 77.626579


def _offset_metres(lat, lng, north=0.0, east=0.0):
    """Shift a point by a distance. Good enough at city scale for a fixture."""
    dlat = north / 111_320.0
    dlng = east / (111_320.0 * 0.9743)          # cos(12.93 degrees)
    return lat + dlat, lng + dlng


# --------------------------------------------------------------------- units
class TestDistance:
    def test_the_same_point_is_zero(self):
        assert haversine_metres(GATE_LAT, GATE_LNG, GATE_LAT, GATE_LNG) == pytest.approx(0, abs=0.01)

    def test_a_hundred_metres_north_measures_a_hundred_metres(self):
        lat, lng = _offset_metres(GATE_LAT, GATE_LNG, north=100)
        assert haversine_metres(GATE_LAT, GATE_LNG, lat, lng) == pytest.approx(100, abs=2)

    def test_a_hundred_metres_east_measures_a_hundred_metres(self):
        # Longitude degrees shrink with latitude. A formula that forgets the
        # cosine passes the north test and fails this one, which is exactly the
        # bug this pair exists to catch.
        lat, lng = _offset_metres(GATE_LAT, GATE_LNG, east=100)
        assert haversine_metres(GATE_LAT, GATE_LNG, lat, lng) == pytest.approx(100, abs=2)

    def test_a_known_long_distance(self):
        # Bengaluru to Delhi, roughly 1,740 km.
        d = haversine_metres(12.9716, 77.5946, 28.6139, 77.2090)
        assert 1_730_000 < d < 1_760_000

    def test_null_island_is_treated_as_missing(self):
        assert not is_valid_coordinate(0.0, 0.0)
        assert not is_valid_coordinate(None, 77.6)
        assert not is_valid_coordinate(12.9, None)
        assert not is_valid_coordinate(91.0, 77.6)
        assert is_valid_coordinate(GATE_LAT, GATE_LNG)


class TestQrPayload:
    def test_round_trip(self):
        raw = qr_payload.encode(qr_payload.KIND_GATE, "abc123xyz")
        assert raw == "PGD1:G:abc123xyz"
        assert qr_payload.parse(raw) == (qr_payload.KIND_GATE, "abc123xyz")

    def test_a_bare_token_still_parses(self):
        # Cards printed before the format existed, and anything typed by hand.
        assert qr_payload.parse("abc123xyz") == (None, "abc123xyz")

    def test_a_foreign_qr_is_not_claimed(self):
        kind, token = qr_payload.parse("upi://pay?pa=someone@bank")
        assert kind is None

    def test_an_unknown_kind_yields_nothing(self):
        assert qr_payload.parse("PGD1:X:abc") == (None, "")

    def test_whitespace_and_case_are_tolerated(self):
        # A barcode gun appends a newline; a phone keyboard capitalises.
        assert qr_payload.parse("  pgd1:r:tok  ") == (qr_payload.KIND_RESIDENT, "tok")

    def test_empty_input_is_safe(self):
        assert qr_payload.parse(None) == (None, "")
        assert qr_payload.parse("   ") == (None, "")


# ---------------------------------------------------------------- integration
@pytest.fixture
def org(db):
    return make_org(db, "Sunrise Living")


@pytest.fixture
def gate(db, org):
    """A positioned branch with self check-in switched on."""
    branch = make_branch(db, org, "Koramangala", "KOR")
    branch.latitude = GATE_LAT
    branch.longitude = GATE_LNG
    branch.geofence_radius_m = 150
    branch.self_checkin_enabled = True
    branch.gate_qr_token = f"gate-{uuid.uuid4().hex[:16]}"
    db.add(OrganizationSettings(organization_id=org.id))
    db.flush()
    return branch


@pytest.fixture
def resident(db, org, gate):
    row = make_customer(db, org, f"rahul-{uuid.uuid4().hex[:8]}@example.com", branch=gate)
    row.qr_token = f"res-{uuid.uuid4().hex[:16]}"
    db.flush()
    return row


def _svc(db, resident):
    return SelfCheckInService(db, resident)


def _payload(branch):
    return qr_payload.encode(qr_payload.KIND_GATE, branch.gate_qr_token)


class TestSelfCheckIn:
    def test_at_the_gate_records_an_entry_and_marks_attendance(
            self, db, gate, resident):
        result = _svc(db, resident).scan(
            _payload(gate), latitude=GATE_LAT, longitude=GATE_LNG, accuracy=10)

        assert result["allowed"] is True
        assert result["direction"] == GateDirection.ENTRY

        log = db.query(GateLog).filter_by(resident_id=resident.id).one()
        assert log.source == "self"
        assert log.allowed is True
        # The position is kept, not just used and discarded - it is the only
        # evidence available if a check-in is later disputed.
        assert log.latitude == pytest.approx(GATE_LAT)
        assert log.distance_m is not None and log.distance_m < 5
        # An entry is the day's attendance. One action, one record.
        assert db.query(Attendance).filter_by(resident_id=resident.id).count() == 1

    def test_the_second_scan_of_the_day_is_an_exit(self, db, gate, resident):
        svc = _svc(db, resident)
        svc.scan(_payload(gate), latitude=GATE_LAT, longitude=GATE_LNG, accuracy=10)

        # Step outside the duplicate window rather than sleeping through it.
        log = db.query(GateLog).filter_by(resident_id=resident.id).one()
        log.occurred_at = datetime.now(timezone.utc) - timedelta(minutes=30)
        db.flush()

        result = svc.scan(_payload(gate), latitude=GATE_LAT, longitude=GATE_LNG, accuracy=10)
        assert result["direction"] == GateDirection.EXIT

    def test_a_scan_from_far_away_is_refused(self, db, gate, resident):
        far_lat, far_lng = _offset_metres(GATE_LAT, GATE_LNG, north=800)
        with pytest.raises(SelfCheckInError) as exc:
            _svc(db, resident).scan(
                _payload(gate), latitude=far_lat, longitude=far_lng, accuracy=10)
        assert exc.value.code == "out_of_range"

        # Refusals are logged. A stream of them is the signal staff would want.
        log = db.query(GateLog).filter_by(resident_id=resident.id).one()
        assert log.allowed is False
        assert log.distance_m > 700
        assert db.query(Attendance).filter_by(resident_id=resident.id).count() == 0

    def test_just_inside_the_fence_passes_and_just_outside_does_not(
            self, db, gate, resident):
        inside_lat, inside_lng = _offset_metres(GATE_LAT, GATE_LNG, north=140)
        assert _svc(db, resident).scan(
            _payload(gate), latitude=inside_lat, longitude=inside_lng,
            accuracy=10)["allowed"] is True

        outside_lat, outside_lng = _offset_metres(GATE_LAT, GATE_LNG, north=170)
        with pytest.raises(SelfCheckInError) as exc:
            _svc(db, resident).scan(
                _payload(gate), latitude=outside_lat, longitude=outside_lng, accuracy=10)
        assert exc.value.code == "out_of_range"

    def test_a_vague_gps_reading_is_refused_rather_than_believed(
            self, db, gate, resident):
        """
        The dangerous case: standing exactly at the gate, but with a reading so
        imprecise it would also be satisfied from streets away. Accepting it
        would make the radius decorative for anyone indoors.
        """
        with pytest.raises(SelfCheckInError) as exc:
            _svc(db, resident).scan(
                _payload(gate), latitude=GATE_LAT, longitude=GATE_LNG,
                accuracy=MAX_ACCURACY_M + 50)
        assert exc.value.code == "weak_gps"

    def test_a_missing_position_cannot_be_omitted_to_skip_the_check(
            self, db, gate, resident):
        """Leaving the coordinates out must not read as "no reason to refuse"."""
        with pytest.raises(SelfCheckInError) as exc:
            _svc(db, resident).scan(
                _payload(gate), latitude=None, longitude=None, accuracy=None)
        assert exc.value.code == "no_location"

    def test_a_double_tap_records_once(self, db, gate, resident):
        svc = _svc(db, resident)
        svc.scan(_payload(gate), latitude=GATE_LAT, longitude=GATE_LNG, accuracy=10)
        again = svc.scan(_payload(gate), latitude=GATE_LAT, longitude=GATE_LNG, accuracy=10)

        assert again["result"] == "duplicate"
        assert again["allowed"] is False
        assert db.query(GateLog).filter_by(
            resident_id=resident.id, allowed=True).count() == 1

    def test_scanning_a_resident_card_is_named_not_just_rejected(
            self, db, gate, resident):
        """An easy mistake. "Not recognised" would send them hunting for a fault."""
        with pytest.raises(SelfCheckInError) as exc:
            _svc(db, resident).scan(
                qr_payload.encode(qr_payload.KIND_RESIDENT, resident.qr_token),
                latitude=GATE_LAT, longitude=GATE_LNG, accuracy=10)
        assert exc.value.code == "wrong_code"

    def test_an_unknown_code_is_refused(self, db, gate, resident):
        with pytest.raises(SelfCheckInError) as exc:
            _svc(db, resident).scan(
                qr_payload.encode(qr_payload.KIND_GATE, "not-a-real-token"),
                latitude=GATE_LAT, longitude=GATE_LNG, accuracy=10)
        assert exc.value.code == "invalid"

    def test_self_checkin_off_refuses_even_from_the_right_spot(
            self, db, gate, resident):
        gate.self_checkin_enabled = False
        db.flush()
        with pytest.raises(SelfCheckInError) as exc:
            _svc(db, resident).scan(
                _payload(gate), latitude=GATE_LAT, longitude=GATE_LNG, accuracy=10)
        assert exc.value.code == "disabled"

    def test_a_checked_out_resident_cannot_check_in(self, db, gate, resident):
        resident.status = CustomerStatus.CHECKED_OUT
        db.flush()
        with pytest.raises(SelfCheckInError) as exc:
            _svc(db, resident).scan(
                _payload(gate), latitude=GATE_LAT, longitude=GATE_LNG, accuracy=10)
        assert exc.value.code == "checked_out"

    def test_status_explains_itself_before_anything_is_scanned(
            self, db, gate, resident):
        far_lat, far_lng = _offset_metres(GATE_LAT, GATE_LNG, north=400)
        blocked = _svc(db, resident).status(far_lat, far_lng, accuracy=10)
        assert blocked["in_range"] is False
        assert blocked["distance_m"] > 350
        # A greyed-out button with no reason is the most common support call.
        assert blocked["reason"]

        here = _svc(db, resident).status(GATE_LAT, GATE_LNG, accuracy=10)
        assert here["in_range"] is True
        assert here["next_direction"] == GateDirection.ENTRY


class TestGateTokenIsolation:
    def test_another_tenants_gate_code_is_not_recognised(
            self, db, gate, resident):
        """
        The isolation case that matters here. Two PGs on the same platform, and
        one resident holding a photograph of the other's poster: the lookup is
        scoped by organisation, so the token simply does not exist for them.
        """
        other_org = make_org(db, "Rival PG")
        other_branch = make_branch(db, other_org, "Indiranagar", "IND")
        other_branch.gate_qr_token = f"gate-{uuid.uuid4().hex[:16]}"
        other_branch.latitude, other_branch.longitude = GATE_LAT, GATE_LNG
        other_branch.self_checkin_enabled = True
        db.flush()

        with pytest.raises(SelfCheckInError) as exc:
            _svc(db, resident).scan(
                _payload(other_branch),
                latitude=GATE_LAT, longitude=GATE_LNG, accuracy=10)
        # "invalid", not "wrong_branch": naming a branch in another tenant would
        # confirm it exists, which is the disclosure the 404 rule exists to stop.
        assert exc.value.code == "invalid"

    def test_a_sibling_branch_is_named_because_it_is_ours(
            self, db, org, gate, resident):
        """
        Inside one organisation the opposite is true: the resident is entitled
        to be told they are at the wrong building of their own PG, and saying so
        discloses nothing across a tenant boundary.
        """
        sibling = make_branch(db, org, "Whitefield", "WHF")
        sibling.gate_qr_token = f"gate-{uuid.uuid4().hex[:16]}"
        db.flush()

        with pytest.raises(SelfCheckInError) as exc:
            _svc(db, resident).scan(
                _payload(sibling), latitude=GATE_LAT, longitude=GATE_LNG, accuracy=10)
        assert exc.value.code == "wrong_branch"
