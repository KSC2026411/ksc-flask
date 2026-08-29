def detect_carrier(container_number):
    prefix=container_number[:4].upper()
    carriers={
        "MSCU":"MSC",
        "MAEU":"MAERSK",
        "CMDU":"CMA_CGM",
        "CMAU":"CMA_CGM",
        "COSU":"COSCO",
        "ONEY":"ONE",
        "EGLV":"EVERGREEN",
        "HLCU":"HAPAG_LLOYD"
    }
    return carriers.get(prefix,"UNKNOWN")