from .carrier_detector import detect_carrier
from .exceptions import TrackingError

def track_container(container_number):
    carrier=detect_carrier(container_number)
    if carrier=="UNKNOWN":
        raise TrackingError("Carrier could not be detected")
    if carrier=="CMA_CGM":
        from .cma import track
        return track(container_number)
    if carrier=="MSC":
        from .msc import track
        return track(container_number)
    if carrier=="MAERSK":
        from .maersk import track
        return track(container_number)
    raise TrackingError("Carrier tracking not implemented yet")