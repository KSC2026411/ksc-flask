from ..exceptions import TrackingUnavailable
def track_generic(reference):
    if not reference:
        raise TrackingUnavailable("Tracking reference missing.")
    return {
        "carrier":"UNKNOWN",
        "reference":reference,
        "status":"NOT_SUPPORTED",
        "message":"Carrier not supported yet."
    }