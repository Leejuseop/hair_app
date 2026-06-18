def synthesize_hair(
    base_profile: dict[str, object],
    style_reference_path: str,
) -> dict[str, object]:
    """Return a placeholder hairstyle synthesis result."""
    return {
        "status": "placeholder",
        "base_profile": base_profile,
        "style_reference_path": style_reference_path,
        "generated_image_path": None,
    }

