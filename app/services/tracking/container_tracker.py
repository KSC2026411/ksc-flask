from .carrier_detector import detect_carrier
from .exceptions import CarrierNotSupported, TrackingError
from .carriers.cma_cgm import track_cma_cgm
from .carriers.maersk import track_maersk
from .carriers.msc import track_msc
from .carriers.generic import track_generic


def track_container(reference):
    if not reference:
        raise TrackingError("Container reference is required.")
    carrier=detect_carrier(reference)
    if carrier=="CMA_CGM":
        return track_cma_cgm(reference)
    if carrier=="MAERSK":
        return track_maersk(reference)
    if carrier=="MSC":
        return track_msc(reference)
    if carrier=="UNKNOWN":
        return track_generic(reference)
    raise CarrierNotSupported(f"Carrier {carrier} is not supported.")