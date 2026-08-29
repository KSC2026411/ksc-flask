import os
import requests


CMA_CGM_API_BASE = os.getenv(
    "CMA_CGM_API_BASE",
    "https://apis.cma-cgm.net"
)

CMA_CGM_API_KEY = os.getenv("CMA_CGM_API_KEY")


class CmaCgmError(Exception):
    pass


def track_cma_cgm(reference):
    """
    Track a CMA CGM shipment/container.

    reference can be a booking reference,
    transport document reference, or equipment/container number.
    """

    if not reference:
        raise CmaCgmError("Tracking reference is required.")

    if not CMA_CGM_API_KEY:
        raise CmaCgmError("CMA_CGM_API_KEY is not configured.")

    reference = reference.strip()

    url = (
        f"{CMA_CGM_API_BASE}"
        "/operation/trackandtrace/v1/events"
    )

    headers = {
        "KeyId": CMA_CGM_API_KEY,
        "Accept": "application/json",
    }

    params = {
        "equipmentReference": reference,
    }

    try:
        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=20,
        )

    except requests.RequestException as exc:
        raise CmaCgmError(
            f"Unable to contact CMA CGM: {exc}"
        ) from exc

    if response.status_code == 429:
        retry_after = response.headers.get(
            "Retry-After",
            "unknown"
        )

        raise CmaCgmError(
            f"CMA CGM rate limit reached. "
            f"Retry after {retry_after} seconds."
        )

    if response.status_code == 401:
        raise CmaCgmError(
            "CMA CGM API authentication failed."
        )

    if response.status_code >= 400:
        raise CmaCgmError(
            f"CMA CGM API returned "
            f"{response.status_code}: {response.text[:500]}"
        )

    try:
        return response.json()

    except ValueError as exc:
        raise CmaCgmError(
            "CMA CGM returned an invalid JSON response."
        ) from exc