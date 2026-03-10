import zipfile
import json
import xml.etree.ElementTree as ET
from pathlib import Path

NS = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
}

def emu_to_inches(value: str | None) -> float | None:
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

def inspect_layout(zf: zipfile.ZipFile, layout_path: str) -> dict:
    root = ET.fromstring(zf.read(layout_path))
    c_sld = root.find("p:cSld", NS)
    layout_name = c_sld.attrib.get("name", Path(layout_path).stem) if c_sld is not None else Path(layout_path).stem

    shapes = []
    for sp in root.findall(".//p:sp", NS):
        nv = sp.find("p:nvSpPr", NS)
        c_nv_pr = nv.find("p:cNvPr", NS) if nv is not None else None
        ph = nv.find(".//p:ph", NS) if nv is not None else None
        xfrm = sp.find("p:spPr/a:xfrm", NS)

        tx_body = sp.find("p:txBody", NS)
        text_runs = [t.text or "" for t in tx_body.findall(".//a:t", NS)] if tx_body is not None else []
        sample_text = " ".join(text_runs).strip()

        shape_info = {
            "shape_id": c_nv_pr.attrib.get("id") if c_nv_pr is not None else None,
            "shape_name": c_nv_pr.attrib.get("name") if c_nv_pr is not None else None,
            "placeholder_type": ph.attrib.get("type") if ph is not None else None,
            "placeholder_idx": ph.attrib.get("idx") if ph is not None else None,
            "sample_text": sample_text[:120],
        }

        if xfrm is not None:
            off = xfrm.find("a:off", NS)
            ext = xfrm.find("a:ext", NS)
            shape_info["x_in"] = emu_to_inches(off.attrib.get("x")) if off is not None else None
            shape_info["y_in"] = emu_to_inches(off.attrib.get("y")) if off is not None else None
            shape_info["w_in"] = emu_to_inches(ext.attrib.get("cx")) if ext is not None else None
            shape_info["h_in"] = emu_to_inches(ext.attrib.get("cy")) if ext is not None else None

        shapes.append(shape_info)

    return {
        "layout_name": layout_name,
        "layout_path": layout_path,
        "placeholders": [s for s in shapes if s["placeholder_type"] is not None],
        "all_shapes": shapes,
    }

def inspect_template(template_path: str, output_path: str = "template_inventory.json") -> None:
    with zipfile.ZipFile(template_path) as zf:
        layouts = [inspect_layout(zf, p) for p in get_layout_parts(zf)]

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
        print(f"{layout['layout_name']}")
        for ph in layout["placeholders"]:
            print(
                f"  - idx={ph['placeholder_idx']!s:<4} "
                f"type={ph['placeholder_type']:<8} "
                f"name={ph['shape_name'] or ''}"
            )
        print()

if __name__ == "__main__":
    inspect_template(
        r"IBM_Consulting_Presentation_Template_2022_V02_Arial.potx",
        "ibm_template_inventory.json"
    )
