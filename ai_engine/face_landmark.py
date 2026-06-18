def detect_landmarks(scan_images: list[str]) -> dict[str, object]:
    """Return placeholder landmark data for guided scan images."""
    return {
        "status": "placeholder",
        "input_count": len(scan_images),
        "landmarks": [],
    }

