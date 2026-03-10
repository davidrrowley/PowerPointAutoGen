import json
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

NS = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}

PLACEHOLDER_NAME_HINTS = (
    "placeholder",
    "content placeholder",
    "text placeholder",
    "picture placeholder",
    "table placeholder",
    "chart placeholder",
)

def emu_to_inches(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    return round(int(value) / 914400, 3)

def get_layout_parts(zf: zipfile.ZipFile) -> list[str]:
    root = ET.fromstring(zf.read("[Content_Types].xml"))
    layout_parts = []
    for child in root:
        if child.tag.endswith("Override"):
            part = child.attrib.get("PartName", "")
            ctype = child.attrib.get("ContentType", "")
            if "slideLayout+xml" in ctype:
                layout_parts.append(part.lstrip("/"))
    return sorted(layout_parts)

def get_layout_name(root: ET.Element, layout_path: str) -> str:
    c_sld = root.find("p:cSld", NS)
    if c_sld is not None:
        name = c_sld.attrib.get("name")
        if name:
            return name
    return Path(layout_path).stem

def get_placeholder_info(nv_container: Optional[ET.Element]) -> tuple[bool, Optional[str], Optional[str]]:
    """
    Returns:
      is_placeholder, placeholder_type, placeholder_idx
    """
    if nv_container is None:
        return False, None, None

    ph = nv_container.find(".//p:ph", NS)
    if ph is None:
        return False, None, None

    ph_type = ph.attrib.get("type")
    ph_idx = ph.attrib.get("idx")

    # In Open XML, placeholder type can be omitted.
    # Treat that as an object/content placeholder.
    if ph_type is None:
        ph_type = "obj"

    return True, ph_type, ph_idx

def get_non_visual_info(shape: ET.Element, shape_tag: str) -> tuple[Optional[str], Optional[str], Optional[ET.Element]]:
    """
    Returns:
      shape_id, shape_name, nv_container
    """
    if shape_tag == "sp":
        nv = shape.find("p:nvSpPr", NS)
        c_nv_pr = nv.find("p:cNvPr", NS) if nv is not None else None
    elif shape_tag == "pic":
        nv = shape.find("p:nvPicPr", NS)
        c_nv_pr = nv.find("p:cNvPr", NS) if nv is not None else None
    elif shape_tag == "graphicFrame":
        nv = shape.find("p:nvGraphicFramePr", NS)
        c_nv_pr = nv.find("p:cNvPr", NS) if nv is not None else None
    elif shape_tag == "grpSp":
        nv = shape.find("p:nvGrpSpPr", NS)
        c_nv_pr = nv.find("p:cNvPr", NS) if nv is not None else None
    else:
        nv = None
        c_nv_pr = None

    shape_id = c_nv_pr.attrib.get("id") if c_nv_pr is not None else None
    shape_name = c_nv_pr.attrib.get("name") if c_nv_pr is not None else None
    return shape_id, shape_name, nv

def get_transform(shape: ET.Element, shape_tag: str) -> dict:
    if shape_tag == "sp":
        xfrm = shape.find("p:spPr/a:xfrm", NS)
    elif shape_tag == "pic":
        xfrm = shape.find("p:spPr/a:xfrm", NS)
    elif shape_tag == "graphicFrame":
        xfrm = shape.find("p:xfrm", NS)
    elif shape_tag == "grpSp":
        xfrm = shape.find("p:grpSpPr/a:xfrm", NS)
    else:
        xfrm = None

    result = {
        "x_in": None,
        "y_in": None,
        "w_in": None,
        "h_in": None,
    }

    if xfrm is not None:
        off = xfrm.find("a:off", NS)
        ext = xfrm.find("a:ext", NS)
        result["x_in"] = emu_to_inches(off.attrib.get("x")) if off is not None else None
        result["y_in"] = emu_to_inches(off.attrib.get("y")) if off is not None else None
        result["w_in"] = emu_to_inches(ext.attrib.get("cx")) if ext is not None else None
        result["h_in"] = emu_to_inches(ext.attrib.get("cy")) if ext is not None else None

    return result

def extract_text(shape: ET.Element) -> str:
    text_runs = [t.text or "" for t in shape.findall(".//a:t", NS)]
    return " ".join(text_runs).strip()

def infer_shape_kind(shape_tag: str, shape: ET.Element) -> str:
    if shape_tag == "sp":
        return "shape"
    if shape_tag == "pic":
        return "picture"
    if shape_tag == "graphicFrame":
        # Try to infer whether this is a table/chart/diagram frame
        uri = shape.find(".//a:graphicData", NS)
        if uri is not None:
            graphic_uri = uri.attrib.get("uri", "")
            if "table" in graphic_uri:
                return "table"
            if "chart" in graphic_uri:
                return "chart"
            if "diagram" in graphic_uri:
                return "diagram"
        return "graphicFrame"
    if shape_tag == "grpSp":
        return "group"
    return shape_tag

def looks_like_placeholder_by_name(shape_name: Optional[str]) -> bool:
    if not shape_name:
        return False
    lowered = shape_name.strip().lower()
    return any(hint in lowered for hint in PLACEHOLDER_NAME_HINTS)

def inspect_shape(shape: ET.Element, shape_tag: str) -> dict:
    shape_id, shape_name, nv = get_non_visual_info(shape, shape_tag)
    is_placeholder_xml, placeholder_type, placeholder_idx = get_placeholder_info(nv)
    text = extract_text(shape)
    transform = get_transform(shape, shape_tag)

    is_placeholder_name = looks_like_placeholder_by_name(shape_name)
    is_placeholder = is_placeholder_xml or is_placeholder_name

    info = {
        "shape_kind": infer_shape_kind(shape_tag, shape),
        "shape_tag": shape_tag,
        "shape_id": shape_id,
        "shape_name": shape_name,
        "is_placeholder": is_placeholder,
        "placeholder_source": (
            "xml"
            if is_placeholder_xml
            else "name_hint"
            if is_placeholder_name
            else None
        ),
        "placeholder_type": placeholder_type,
        "placeholder_idx": placeholder_idx,
        "has_text": bool(text),
        "sample_text": text[:200],
        **transform,
    }

    return info

def iter_shapes(root: ET.Element) -> list[dict]:
    sp_tree = root.find(".//p:spTree", NS)
    if sp_tree is None:
        return []

    shapes = []
    for child in sp_tree:
        tag = child.tag.split("}", 1)[-1]
        if tag in {"sp", "pic", "graphicFrame", "grpSp"}:
            shapes.append(inspect_shape(child, tag))
    return shapes

def inspect_layout(zf: zipfile.ZipFile, layout_path: str) -> dict:
    root = ET.fromstring(zf.read(layout_path))
    layout_name = get_layout_name(root, layout_path)
    shapes = iter_shapes(root)

    placeholders = [s for s in shapes if s["is_placeholder"]]

    return {
        "layout_name": layout_name,
        "layout_path": layout_path,
        "placeholder_count": len(placeholders),
        "shape_count": len(shapes),
        "placeholders": placeholders,
        "all_shapes": shapes,
    }

def inspect_template(template_path: str, output_path: str = "template_inventory_v2.json") -> None:
    with zipfile.ZipFile(template_path) as zf:
        layout_paths = get_layout_parts(zf)
        layouts = [inspect_layout(zf, p) for p in layout_paths]

    result = {
        "template_file": template_path,
        "layout_count": len(layouts),
        "layouts": layouts,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(f"Wrote inventory to {output_path}")
    print(f"Found {len(layouts)} layouts")
    print()

    for layout in layouts:
        print(f"{layout['layout_name']} ({layout['placeholder_count']} placeholders / {layout['shape_count']} shapes)")
        for ph in layout["placeholders"]:
            print(
                f"  - id={str(ph['shape_id']):<4} "
                f"idx={str(ph['placeholder_idx']):<4} "
                f"type={str(ph['placeholder_type']):<8} "
                f"kind={ph['shape_kind']:<12} "
                f"src={str(ph['placeholder_source']):<9} "
                f"name={ph['shape_name'] or ''}"
            )
        print()

if __name__ == "__main__":
    inspect_template(
        r"IBM_Consulting_Presentation_Template_2022_V02_Arial.potx",
        "ibm_template_inventory_v2.json"
    )