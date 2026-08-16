"""
CSV export helper.

Extracted from the duplicated io.StringIO + csv.writer + Response
boilerplate in app.py's api_oil_maintenance_export() and
api_fuel_log_export() (Section 6.4.1, Phase 7). Both endpoints built this
exact same pattern independently; this is the first shared implementation.
"""
import csv
import io

from flask import Response


def csv_response(headers: list, rows: list, filename: str) -> Response:
    """Build a CSV download response from a header row and data rows.

    Uses utf-8-sig encoding so the file opens correctly with accented/
    Vietnamese text in Excel, matching both original export endpoints.
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)

    csv_bytes = output.getvalue().encode("utf-8-sig")
    return Response(
        csv_bytes,
        mimetype="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
