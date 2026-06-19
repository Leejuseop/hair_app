# Idea Evolution

Hair App started as a simple mobile web MVP: scan the user, upload a hairstyle reference, and show a generated preview.

The direction evolved after discussing quality limits. A direct two-image hair transfer API might accept only:

- One user photo.
- One hairstyle reference photo.
- One generated output.

That is useful for a demo, but it may not leave room for our personal base profile data unless we control the preprocessing, model workflow, or open-source inference code.

## Current Direction

The project is now moving toward this pipeline:

1. Guided scan creates a personal base profile.
2. The base profile stores raw landmarks, best frames, derived metrics, and synthesis anchors.
3. Open-source hairstyle synthesis models are tested in Colab.
4. The chosen model is modified or wrapped so it can use our scan-derived data.

The base profile is not the final 3D avatar. It is the first structured user representation that future synthesis experiments can consume.

## Why Not Only a Generic API

A closed third-party API may not let us inject:

- Landmark constraints.
- Hairline anchor points.
- Face masks.
- Side-profile information.
- Scan quality data.
- Custom preprocessing steps.

Because of that, the preferred direction is to test open-source hair transfer models and tune or modify them directly.

## Current Model Priority

Performance-first research priority:

1. `StableHairV2` / `HairPort`
2. `Stable-Hair`
3. `HairFusion`
4. `HairFastGAN`

`StableHairV2` and `HairPort` look closest to the long-term high-quality direction. `Stable-Hair` is likely a strong practical candidate for early Colab experiments. `HairFastGAN` remains useful as a fast baseline, but probably not the highest-quality final path.

## Current Decision

Keep the web MVP simple, but make the scan/base-profile data real. Do not build the full synthesis engine yet. First, validate the scan data and then test which open-source model can be adapted to use that data.
