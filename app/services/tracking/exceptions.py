class TrackingError(Exception):
    pass


class CarrierNotSupported(TrackingError):
    pass


class TrackingUnavailable(TrackingError):
    pass