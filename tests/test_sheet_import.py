"""
Tests for services/delivery/sheet_import_service.py — the Google Sheet
dispatch-plan extractor.

No test here touches the network. ``fetch_plan_for_date`` takes an injected
fetcher, and the fixture in ``tests/fixtures/huwei_plan_th08.json`` is a gviz
payload built from rows copied out of the live sheet on 2026-08-09, including
its real defects: three coordinate formats, a blank-date continuation row, a
missing station code, a non-numeric priority, and a ``01-th8`` date cell.

The reference date used throughout is 2026-08-10 — the day whose plan was
actually in the sheet when this was written.
"""

import json
from datetime import date
from pathlib import Path

import pytest

from services.delivery import sheet_import_service as sis

FIXTURE = Path(__file__).parent / "fixtures" / "huwei_plan_th08.json"
TARGET = date(2026, 8, 10)


@pytest.fixture
def payload():
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def fetcher(payload):
    """Stands in for fetch_tab; records which tabs were asked for."""
    calls = []

    def _fetch(tab_name, sheet_id=None, timeout=None):
        calls.append(tab_name)
        if tab_name == "TH08":
            return payload
        raise sis.SheetTabMissing(f"no such tab: {tab_name}")

    _fetch.calls = calls
    return _fetch


@pytest.fixture
def extracted(payload):
    labels, rows = sis.grid_from_payload(payload)
    return sis.extract_day(rows, TARGET, tab_name="TH08")


def _by_station(result, code):
    return next(r for r in result.rows if r["station_code"] == code)


def _warnings_for(result, field):
    return [w for w in result.warnings if w.field == field]


# ---------------------------------------------------------------------------
# Coordinate repair
# ---------------------------------------------------------------------------
class TestParseCoordinate:
    """The three formats the sheet actually uses, plus the failure modes."""

    @pytest.mark.parametrize("raw,kind,expected", [
        # Comma decimal separator (Vietnamese locale).
        ("9,636058", "lat", 9.636058),
        ("106,491648", "lng", 106.491648),
        ("9,97482", "lat", 9.97482),
        # Already clean.
        ("9.60967", "lat", 9.60967),
        ("105.9544", "lng", 105.9544),
        ("10.4568", "lat", 10.4568),
        # Decimal point lost to thousands-separator formatting. These are the
        # dangerous ones: float() raises on the first and silently returns 1.06
        # on the second if the dots are naively stripped to one.
        ("9.585.868", "lat", 9.585868),
        ("1.059.744", "lng", 105.9744),
        ("9.591.387", "lat", 9.591387),
        ("1.059.742", "lng", 105.9742),
        # Whitespace and stray characters.
        ("  10.08466  ", "lat", 10.08466),
    ])
    def test_recovers_value(self, raw, kind, expected):
        value, problem = sis.parse_coordinate(raw, kind)
        assert problem is None
        assert value == pytest.approx(expected)

    def test_already_numeric_passes_through(self):
        assert sis.parse_coordinate(10.4568, "lat") == (10.4568, None)

    @pytest.mark.parametrize("raw,kind", [
        ("", "lat"),
        (None, "lng"),
        ("   ", "lat"),
        ("chưa có", "lat"),          # prose, no digits
        ("999.9", "lng"),            # no placement lands inside Vietnam
        ("48.8566", "lat"),          # Paris — plausible number, wrong country
        (48.8566, "lat"),            # ditto, already numeric
        ("2.3522", "lng"),           # Paris longitude
    ])
    def test_refuses_rather_than_guesses(self, raw, kind):
        value, problem = sis.parse_coordinate(raw, kind)
        assert value is None
        assert problem  # a reason the dispatcher can read

    def test_out_of_country_message_names_the_window(self):
        _, problem = sis.parse_coordinate("48.8566", "lat")
        assert "8.0" in problem and "24.0" in problem

    def test_repair_is_unambiguous_within_a_column(self):
        """The property the repair actually rests on.

        For a given digit string there is at most one decimal placement inside
        the latitude window, and at most one inside the longitude window. It is
        *not* true that a digit string is valid for only one of the two — the
        longitude 105.9744 also reads as the latitude 10.59744 — which is why
        the column being parsed is passed in explicitly rather than sniffed.
        """
        for kind in ("lat", "lng"):
            low, high = (sis.VN_LAT_RANGE if kind == "lat" else sis.VN_LNG_RANGE)
            for digits in ("1059744", "9585868", "104568", "1045", "9912", "11055"):
                placements = []
                for split in (1, 2, 3):
                    whole, frac = digits[:split], digits[split:]
                    value = float(f"{whole}.{frac}") if frac else float(whole)
                    if low <= value <= high:
                        placements.append(value)
                assert len(placements) <= 1, (kind, digits, placements)

    def test_the_same_digits_read_differently_per_column(self):
        assert sis.parse_coordinate("1.059.744", "lng")[0] == pytest.approx(105.9744)
        assert sis.parse_coordinate("1.059.744", "lat")[0] == pytest.approx(10.59744)


# ---------------------------------------------------------------------------
# Date parsing and year inference
# ---------------------------------------------------------------------------
class TestParseSheetDate:

    @pytest.mark.parametrize("text,expected", [
        ("10-Aug", date(2026, 8, 10)),
        ("2-Aug", date(2026, 8, 2)),        # no leading zero
        ("02-Aug", date(2026, 8, 2)),
        ("21-Jul", date(2026, 7, 21)),
        ("01-th8", date(2026, 8, 1)),       # Vietnamese 'tháng 8'
        ("1-thang8", date(2026, 8, 1)),
        ("10-8", date(2026, 8, 10)),        # numeric, day-first
        ("10/08", date(2026, 8, 10)),
        ("10 August", date(2026, 8, 10)),
    ])
    def test_forms_seen_in_the_sheet(self, text, expected):
        parsed, warning = sis.parse_sheet_date(text, TARGET)
        assert parsed == expected
        assert warning is None

    @pytest.mark.parametrize("text", ["", None, "   ", "tuần sau", "Aug", "31-Feb"])
    def test_unparseable_returns_none_with_a_reason(self, text):
        parsed, warning = sis.parse_sheet_date(text, TARGET)
        assert parsed is None
        assert warning

    def test_year_is_inferred_from_the_reference(self):
        parsed, _ = sis.parse_sheet_date("10-Aug", date(2027, 8, 9))
        assert parsed == date(2027, 8, 10)

    def test_year_rolls_back_across_the_january_boundary(self):
        """A 28-Dec cell read on 2 Jan belongs to the year that just ended."""
        parsed, warning = sis.parse_sheet_date("28-Dec", date(2027, 1, 2))
        assert parsed == date(2026, 12, 28)
        assert warning is None

    def test_year_rolls_forward_across_the_december_boundary(self):
        parsed, warning = sis.parse_sheet_date("2-Jan", date(2026, 12, 30))
        assert parsed == date(2027, 1, 2)
        assert warning is None

    def test_inference_far_from_the_reference_is_flagged_not_silent(self):
        """The requested change: never infer a year without validating it.

        25-Dec read while planning 10-Aug is 137 days away — outside the
        window, so the value is still returned but the dispatcher is told the
        year is a guess.
        """
        parsed, warning = sis.parse_sheet_date("25-Dec", TARGET)
        assert parsed == date(2026, 12, 25)
        assert warning is not None
        assert "137 days" in warning
        assert "2026-08-10" in warning

    def test_dates_inside_the_window_are_not_flagged(self):
        for text in ("21-Jul", "01-th8", "9-Aug", "30-Sep"):
            parsed, warning = sis.parse_sheet_date(text, TARGET)
            assert parsed is not None, text
            assert warning is None, (text, warning)

    def test_29_february_is_attributed_to_the_leap_year(self):
        parsed, _ = sis.parse_sheet_date("29-Feb", date(2028, 3, 1))
        assert parsed == date(2028, 2, 29)


# ---------------------------------------------------------------------------
# Phone normalization
#
# The phone columns are text in some rows and number-formatted in others. A
# numeric cell arrives corrupted twice over — Sheets drops the leading zero,
# and gviz hands us a float whose ".0" the old digit-strip welded onto the end.
# Both were found in production on 2026-08-15: 118 of 149 stored manager
# phones were malformed, and 85 of those carried the welded zero — 85 of 85,
# which is what identified the float rather than dispatcher typing.
# ---------------------------------------------------------------------------
class TestCleanPhone:

    def test_spaces_are_stripped(self):
        assert sis._clean_phone("0939 980 584") == "0939980584"

    def test_a_correct_text_cell_is_left_alone(self):
        assert sis._clean_phone("0907785256") == "0907785256"

    def test_leading_zero_is_restored_on_a_numeric_cell(self):
        # Sheets stores 0939746130 as the integer 939746130.
        assert sis._clean_phone("939746130") == "0939746130"

    def test_float_fraction_does_not_become_a_trailing_digit(self):
        # gviz reports the numeric cell as 939746130.0; str() keeps the ".0",
        # and stripping non-digits used to yield "9397461300".
        assert sis._clean_phone("939746130.0") == "0939746130"

    def test_comma_decimal_float_is_handled_too(self):
        assert sis._clean_phone("939746130,0") == "0939746130"

    def test_the_three_stored_forms_of_one_number_agree(self):
        # One manager, 14 stops, three spellings in the live database.
        forms = ["0939746130", "939746130", "939746130.0"]
        assert {sis._clean_phone(f) for f in forms} == {"0939746130"}

    def test_a_ten_digit_number_is_not_given_a_second_zero(self):
        assert sis._clean_phone("0939568724") == "0939568724"

    def test_country_prefixed_number_keeps_its_plus(self):
        assert sis._clean_phone("+84939746130") == "+84939746130"

    def test_empty_and_none_stay_empty(self):
        assert sis._clean_phone("") == ""
        assert sis._clean_phone(None) == ""

    def test_a_real_decimal_is_not_mistaken_for_the_artifact(self):
        # Only an all-zero fraction is the float artifact. Anything else falls
        # through to the original digit strip rather than being reinterpreted.
        assert sis._clean_phone("939746130.5") == "9397461305"


# ---------------------------------------------------------------------------
# Tab selection
# ---------------------------------------------------------------------------
class TestCandidateTabs:

    def test_month_tab_first_then_previous(self):
        assert sis.candidate_tabs(date(2026, 8, 10)) == ["TH08", "TH07"]

    def test_january_falls_back_to_december(self):
        assert sis.candidate_tabs(date(2026, 1, 3)) == ["TH01", "TH12"]


# ---------------------------------------------------------------------------
# gviz envelope and layout guard
# ---------------------------------------------------------------------------
class TestPayloadHandling:

    def test_unwraps_the_setresponse_envelope(self):
        body = ('/*O_o*/\ngoogle.visualization.Query.setResponse('
                '{"status":"ok","table":{"cols":[],"rows":[]}});')
        assert sis._parse_gviz_payload(body)["status"] == "ok"

    def test_html_login_page_is_a_fetch_error_not_a_crash(self):
        with pytest.raises(sis.SheetFetchError):
            sis._parse_gviz_payload("<html><body>Sign in</body></html>")

    def test_google_query_error_is_surfaced(self):
        body = ('google.visualization.Query.setResponse({"status":"error",'
                '"errors":[{"detailed_message":"Invalid query: bad"}]});')
        with pytest.raises(sis.SheetFetchError) as exc:
            sis._parse_gviz_payload(body)
        assert "Invalid query" in str(exc.value)

    def test_layout_passes_on_the_real_header_row(self, payload):
        labels, _ = sis.grid_from_payload(payload)
        sis.validate_layout(labels)  # must not raise

    def test_reordered_columns_are_refused(self, payload):
        labels, _ = sis.grid_from_payload(payload)
        labels[11], labels[13] = labels[13], labels[11]  # LAT <-> address
        with pytest.raises(sis.SheetLayoutError) as exc:
            sis.validate_layout(labels)
        assert "column L" in str(exc.value)

    def test_inserted_column_is_refused(self, payload):
        """An inserted column shifts everything right of it.

        Without this guard, coordinates would be read out of the address column
        and the import would produce plausible-looking nonsense.
        """
        labels, _ = sis.grid_from_payload(payload)
        labels.insert(2, "CỘT MỚI")
        with pytest.raises(sis.SheetLayoutError):
            sis.validate_layout(labels)


# ---------------------------------------------------------------------------
# End-to-end extraction of one day
# ---------------------------------------------------------------------------
class TestExtractDay:

    def test_only_the_requested_day_is_returned(self, extracted):
        codes = [r["station_code"] for r in extracted.rows]
        assert codes == [
            "STST28", "STST27", "STST15", "",          # 50H-939.63
            "AGCT33", "AGCT26", "Non HW Delivery-DU",  # 50H-197.93
            "KGGRX2", "CTCD15",                        # 50H-791.07
        ]
        assert "TVDI10" not in codes   # 21-Jul
        assert "VLVM45" not in codes   # 01-th8
        assert "KGHT02" not in codes   # 25-Dec

    def test_plate_and_driver_are_forward_filled_down_each_block(self, extracted):
        assert [r["vehicle"] for r in extracted.rows] == [
            "50H-939.63"] * 4 + ["50H-197.93"] * 3 + ["50H-791.07"] * 2
        assert _by_station(extracted, "STST15")["driver_name"] == "NGÔ HỮU QUÍ"
        assert _by_station(extracted, "CTCD15")["driver_name"] == "TRẦN HOÀNG QUÂN"

    def test_blank_date_continuation_row_belongs_to_the_day_above(self, extracted):
        """STST27's date cell is empty in the sheet; it is still a 10-Aug stop."""
        stop = _by_station(extracted, "STST27")
        assert stop["sequence"] == 2
        assert stop["vehicle"] == "50H-939.63"

    def test_separator_rows_are_skipped(self, extracted):
        assert all(any(r.values()) for r in extracted.rows)
        assert len(extracted.rows) == 9

    def test_coordinates_are_repaired(self, extracted):
        stop = _by_station(extracted, "STST28")
        assert stop["lat"] == pytest.approx(9.585868)
        assert stop["lng"] == pytest.approx(105.9744)

    def test_a_stop_with_no_coordinates_is_kept_and_warned_about(self, extracted):
        """The operator's choice: keep the stop, leave coordinates empty, warn."""
        stop = _by_station(extracted, "AGCT26")
        assert stop["lat"] is None and stop["lng"] is None
        warning = next(w for w in _warnings_for(extracted, "coordinates")
                       if w.station_code == "AGCT26")
        assert "no map marker" in warning.message

    def test_an_unrepairable_coordinate_drops_both_halves(self, extracted):
        """`Non HW Delivery-DU` has a valid latitude and a junk longitude.

        Keeping the latitude alone would put the stop on the prime meridian,
        which reads as real data on the dashboard. Both go.
        """
        stop = _by_station(extracted, "Non HW Delivery-DU")
        assert stop["lat"] is None and stop["lng"] is None
        assert _warnings_for(extracted, "coordinates")

    def test_non_huawei_rows_are_imported_as_stops(self, extracted):
        assert _by_station(extracted, "Non HW Delivery-DU")["sequence"] == 3

    def test_missing_station_code_is_imported_with_a_warning(self, extracted):
        blank = [r for r in extracted.rows if r["station_code"] == ""]
        assert len(blank) == 1
        assert blank[0]["address"].startswith("KDC Minh Châu")
        assert len(_warnings_for(extracted, "station_code")) == 1

    def test_non_numeric_priority_falls_back_to_position(self, extracted):
        stop = _by_station(extracted, "CTCD15")
        assert stop["sequence"] == 2
        assert _warnings_for(extracted, "sequence")

    def test_empty_address_falls_back_to_district_and_province(self, extracted):
        stop = _by_station(extracted, "Non HW Delivery-DU")
        assert stop["address"] == "ChâuThành, An Giang"
        assert _warnings_for(extracted, "address")

    def test_note_joins_incident_and_trailing_columns_and_drops_filler(self, extracted):
        stop = _by_station(extracted, "STST28")
        parts = stop["note"].split("\t")
        assert parts[0] == "dô hẻm cỡ gần 200m"
        assert "Để được trong phòng máy thiết bị" in parts
        assert "0" not in parts
        assert "#N/A" not in stop["note"]

    def test_no_incident_sentinel_is_not_copied_into_the_note(self, extracted):
        stop = _by_station(extracted, "Non HW Delivery-DU")
        assert "KHÔNG CÓ PHÁT SINH" not in stop["note"]

    def test_manager_phone_spaces_are_stripped(self, extracted):
        assert _by_station(extracted, "KGGRX2")["manager_phone"] == "0939980584"

    def test_station_name_mirrors_the_code(self, extracted):
        stop = _by_station(extracted, "AGCT33")
        assert stop["station_name"] == stop["station_code"] == "AGCT33"

    def test_product_description_comes_from_so_kgs(self, extracted):
        assert _by_station(extracted, "STST27")["product_description"] == (
            "Newbuild 5G Single 3.8 64T")

    def test_rows_carry_their_sheet_row_for_traceability(self, extracted):
        assert _by_station(extracted, "STST28")["sheet_row"] == 5

    def test_far_off_date_cell_is_reported_once(self, extracted):
        """The 25-Dec row is not part of the day, but the year guess is flagged."""
        date_warnings = _warnings_for(extracted, "date")
        assert len(date_warnings) == 1
        assert "25-Dec" in date_warnings[0].message

    def test_shape_matches_what_plan_service_consumes(self, extracted):
        required = {"vehicle", "sequence", "station_code", "station_name",
                    "address", "lat", "lng", "manager_name", "manager_phone",
                    "product_description", "note"}
        for row in extracted.rows:
            assert required <= set(row)


# ---------------------------------------------------------------------------
# Tab search
# ---------------------------------------------------------------------------
class TestFetchPlanForDate:

    def test_finds_the_day_in_the_month_tab(self, fetcher):
        result = sis.fetch_plan_for_date(TARGET, fetcher=fetcher)
        assert result.tab_name == "TH08"
        assert len(result.rows) == 9
        assert fetcher.calls == ["TH08"]

    def test_falls_through_to_the_previous_month_tab(self, payload):
        """On the 1st, this month's tab may not exist yet."""
        calls = []

        def _fetch(tab_name, sheet_id=None, timeout=None):
            calls.append(tab_name)
            if tab_name == "TH09":
                raise sis.SheetTabMissing("no such tab")
            return payload

        result = sis.fetch_plan_for_date(
            date(2026, 8, 10), tab_names=["TH09", "TH08"], fetcher=_fetch)
        assert calls == ["TH09", "TH08"]
        assert result.tab_name == "TH08"

    def test_an_outage_is_not_reported_as_an_empty_day(self):
        """A network failure and an unfilled sheet demand opposite responses.

        The tab search tolerates a missing worksheet, so it must not also
        swallow a real fetch failure — that turned "the network is down" into
        "no plan for that date", pointing the dispatcher at the wrong problem.
        """
        def _fetch(tab_name, sheet_id=None, timeout=None):
            raise sis.SheetFetchError("Could not reach the Google Sheet: timeout")

        with pytest.raises(sis.SheetFetchError) as exc:
            sis.fetch_plan_for_date(TARGET, fetcher=_fetch)
        assert not isinstance(exc.value, sis.SheetDateNotFound)

    def test_a_missing_worksheet_is_recognised_from_googles_message(self):
        body = ('google.visualization.Query.setResponse({"status":"error",'
                '"errors":[{"reason":"invalid_query","detailed_message":'
                '"Invalid sheet name: TH09"}]});')
        with pytest.raises(sis.SheetTabMissing):
            sis._parse_gviz_payload(body)

    def test_other_query_errors_stay_plain_fetch_errors(self):
        body = ('google.visualization.Query.setResponse({"status":"error",'
                '"errors":[{"reason":"invalid_query","detailed_message":'
                '"Invalid query: bad column"}]});')
        with pytest.raises(sis.SheetFetchError) as exc:
            sis._parse_gviz_payload(body)
        assert not isinstance(exc.value, sis.SheetTabMissing)

    def test_a_date_with_no_rows_raises_with_the_tabs_it_tried(self, fetcher):
        with pytest.raises(sis.SheetDateNotFound) as exc:
            sis.fetch_plan_for_date(date(2026, 8, 31), fetcher=fetcher)
        assert "2026-08-31" in str(exc.value)
        assert "TH08" in str(exc.value)

    def test_layout_error_is_not_swallowed_by_the_tab_search(self, payload):
        """A changed layout must fail loudly, not look like an empty tab."""
        broken = json.loads(json.dumps(payload))
        broken["table"]["cols"][11]["label"] = "Ghi chú thêm"
        with pytest.raises(sis.SheetLayoutError):
            sis.fetch_plan_for_date(
                TARGET, tab_names=["TH08"],
                fetcher=lambda *a, **k: broken)

    def test_result_serialises_for_the_api(self, fetcher):
        payload = sis.fetch_plan_for_date(TARGET, fetcher=fetcher).as_dict()
        assert set(payload) == {"rows", "warnings", "tab_name"}
        assert all(set(w) == {"sheet_row", "field", "message", "station_code"}
                   for w in payload["warnings"])
        json.dumps(payload)  # must be JSON-serialisable for jsonify
