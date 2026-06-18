def build_base_profile(landmark_data: dict[str, object]) -> dict[str, object]:
    """Return a placeholder personal base profile."""
    return {
        "status": "placeholder",
        "source": landmark_data,
        "profile": None,
    }

