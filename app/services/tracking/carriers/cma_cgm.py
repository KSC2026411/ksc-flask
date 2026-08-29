import os
import requests
from ..exceptions import TrackingUnavailable
CMA_CGM_API_BASE=os.getenv("CMA_CGM_API_BASE","https://apis.cma-cgm.net")
CMA_CGM_API_KEY=os.getenv("CMA_CGM_API_KEY")
def track_cma_cgm(reference):
    if not reference:
        raise TrackingUnavailable("Tracking reference is required.")
    if not CMA_CGM_API_KEY:
        raise TrackingUnavailable("CMA CGM API key is not configured.")
    url=f"{CMA_CGM_API_BASE}/operation/trackandtrace/v1/events"
    headers={
        "KeyId":CMA_CGM_API_KEY,
        "Accept":"application/json"
    }
    params={
        "equipmentReference":reference
    }
    try:
        response=requests.get(
            url,
            headers=headers,
            params=params,
            timeout=20
        )
    except requests.RequestException as exc:
        raise TrackingUnavailable(
            f"CMA CGM connection failed: {exc}"
        )
    if response.status_code==401:
        raise TrackingUnavailable(
            "CMA CGM authentication failed."
        )
    if response.status_code>=400:
        raise TrackingUnavailable(
            f"CMA CGM error {response.status_code}: {response.text[:300]}"
        )
    try:
        return response.json()
    except ValueError:
        raise TrackingUnavailable(
            "CMA CGM returned invalid JSON."
        )