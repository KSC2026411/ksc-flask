def format_tracking_result(data, tracking_number):
    return {
        "tracking_number": tracking_number,
        "status": extract_status(data),
        "location": extract_location(data),
        "eta": extract_eta(data),
        "updated": extract_update_time(data)
    }