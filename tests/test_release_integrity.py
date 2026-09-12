from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]


def test_build_label_has_single_source_of_truth():
    source = (ROOT / "gp_ui.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    values = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "BUILD":
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                        values.append(node.value.value)
                    else:
                        values.append(None)
    assert len(values) == 1, f"BUILD must be assigned exactly once, found {values}"
    assert values[0] and values[0].startswith("GP-CLOUD-v")


def test_streamlit_entrypoint_uses_gp_ui_build_value():
    tree = ast.parse((ROOT / "inventory_tracker.py").read_text(encoding="utf-8"))
    imports_build = False
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "gp_ui":
            imports_build = any(alias.name == "BUILD" for alias in node.names)
            if imports_build:
                break
    assert imports_build, "inventory_tracker.py must import BUILD from gp_ui"
