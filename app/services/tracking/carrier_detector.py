def detect_carrier(container_number):
    if not container_number:
        return "UNKNOWN"

    container_number = container_number.strip().upper()

    if len(container_number) < 4:
        return "UNKNOWN"

    prefix = container_number[:4]

    carriers = {
        "MSCU": "MSC",
        "MAEU": "MAERSK",
        "CMDU": "CMA_CGM",
        "CMAU": "CMA_CGM",
        "COSU": "COSCO",
        "ONEY": "ONE",
        "EGLV": "EVERGREEN",
        "HLCU": "HAPAG_LLOYD",
        "SEGU": "SEACO",
        "TRIU": "TRITON",
        "TGHU": "TEXTAINER",
        "CAIU": "CAI",
        "TEMU": "TEMU",
        "UACU": "UASC"
    }

    return carriers.get(prefix, "UNKNOWN")