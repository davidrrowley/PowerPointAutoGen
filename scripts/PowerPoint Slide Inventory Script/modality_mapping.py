from __future__ import annotations

from layout_catalogue import load_layout_catalogue
from pattern_resolver import resolve_layout_for_modality


def resolve_layout_name_from_catalogue(
    modality: str,
    catalogue_path: str = "layout_catalogue.yaml",
) -> tuple[str, str]:
    catalogue = load_layout_catalogue(catalogue_path)
    result = resolve_layout_for_modality(modality, catalogue)
    return result["pattern"], result["layout"]["name"]