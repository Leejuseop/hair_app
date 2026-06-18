def refine_result(generated_image_path: str | None) -> dict[str, object]:
    """Return placeholder post-processing metadata."""
    return {
        "status": "placeholder",
        "input_image_path": generated_image_path,
        "output_image_path": generated_image_path,
    }

