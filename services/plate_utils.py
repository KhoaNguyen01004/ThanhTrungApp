"""
License plate normalization utilities.

Vietnamese plates follow the pattern ``XX-XXXXX``: a two-digit province code,
one or two series letters, then the serial. This module extracts that trailing
serial so the ``50E-18463`` / ``50E18463`` / ``50E 18463`` / bare ``18463``
variants that TTAS, the Google Sheet and the ``vehicles`` table disagree about
all resolve to one key.

**The serial is not globally unique, and this module does not pretend it is.**
It carries no province code, so ``50H-09473`` and ``51C-09473`` normalize to
the same ``09473``. Callers own that collision, and the two that index by it
already handle it explicitly:

* ``services.vehicle_identity.VehicleIndex`` collects colliding serials in
  ``_ambiguous_serials``, logs them, and refuses to resolve — a wrong match
  would attach delivery stops to the wrong truck.
* ``services.delivery.routes._gps_by_plate_key`` logs and keeps the first,
  since two GPS devices reporting the same serial is a data problem to be
  seen rather than silently averaged.

Verified 2026-08-06: 36 vehicles, zero collisions, and all 31 distinct
``fuel_log`` plates resolve. The risk is real but not currently realised.

One more edge worth knowing: every digit in the string counts, so trailing
digits that are not part of the plate corrupt the key — ``"51C-12345 (xe 2)"``
yields ``23452``, not ``12345``. Pass a plate, not a free-text label.
"""

import re
from typing import Optional


def normalize_plate(plate: Optional[str]) -> str:
    """Extract the trailing 5-digit serial from a license plate.

    Examples::

        normalize_plate("50H-09473")  ->  "09473"
        normalize_plate("09473")      ->  "09473"
        normalize_plate("50E18463")   ->  "18463"
        normalize_plate("18463")      ->  "18463"
        normalize_plate("")           ->  ""
        normalize_plate(None)         ->  ""

    Returns the last 5 digits found in the string, or the full digit
    sequence if it is shorter than 5 characters.
    """
    if not plate:
        return ""
    digits = re.sub(r"[^0-9]", "", plate)
    return digits[-5:] if len(digits) >= 5 else digits
