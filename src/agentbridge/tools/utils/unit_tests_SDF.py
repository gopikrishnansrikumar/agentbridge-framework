import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

import requests  # kept for future/optional use
import xmlschema  # kept for future/optional use
from lxml import etree  # kept for future/optional use


class SDFTestReport:
    def __init__(self, sdf_file):
        self.sdf_file = sdf_file
        self.tests = []
        self.results = []
        self.sdf_root = None
        self.first_parse_error = None  # (msg, line, col)

    def add_test(self, func, description):
        self.tests.append((func, description))

    def run_all(self):
        self.results.clear()
        for func, desc in self.tests:
            try:
                res, msg, parse_error = func()
                if parse_error and not self.first_parse_error:
                    self.first_parse_error = parse_error
                self.results.append(f"{'✅' if res else '❌'} {desc}: {msg}")
            except Exception as e:
                self.results.append(f"❌ {desc}: Exception {e}")

    def report(self):
        output = "\n".join(self.results)
        if self.first_parse_error:
            msg, line, col = self.first_parse_error
            context = get_context_lines(self.sdf_file, line)
            output += f"\n\nFirst XML Parse Error:\n{msg} at line {line}, col {col}\nContext:\n{context}"
        return output

    def report_markdown(self):
        """Return the report as Markdown (better for GUI rendering)."""
        lines = []
        lines.append("# SDF Test Report")
        lines.append(f"**File:** `{self.sdf_file}`\n")
        lines.append("## Results")
        for r in self.results:
            lines.append(f"- {r}")

        if self.first_parse_error:
            msg, line, col = self.first_parse_error
            context = get_context_lines(self.sdf_file, line)
            lines.append("\n## First XML Parse Error")
            lines.append(f"- **Message:** `{msg}`")
            lines.append(f"- **Location:** line **{line}**, col **{col}**")
            lines.append("\n**Context:**")
            lines.append("```xml")
            lines.append(context.rstrip("\n"))
            lines.append("```")

        return "\n".join(lines)

    def load_root(self):
        if self.sdf_root is None:
            try:
                tree = ET.parse(self.sdf_file)
                self.sdf_root = tree.getroot()
            except Exception:
                self.sdf_root = None
        return self.sdf_root


def get_context_lines(file_path, error_line, context=3):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        start = max(0, error_line - context - 1)
        end = min(len(lines), error_line + context)
        excerpt = "".join(
            f"{i+1:>4}: {line}" for i, line in enumerate(lines[start:end], start=start)
        )
        return excerpt
    except Exception as e:
        return f"Could not read lines from file: {e}"


# ---- TEST FUNCTIONS ----
# All test functions return (result, message, parse_error)
# where parse_error is (msg, line, col) or None


def test_xml_well_formed(sdf_file):
    def f():
        try:
            ET.parse(sdf_file)
            return True, "XML is well-formed", None
        except ET.ParseError as e:
            if hasattr(e, "position"):
                line, col = e.position
                msg = f"XML Parse Error: {e}"
                return False, f"{msg} at line {line}, col {col}", (msg, line, col)
            else:
                msg = f"XML Parse Error: {e}"
                return False, msg, (msg, 0, 0)

    return f


def test_required_tags(sdf_file, required_tags=("model", "link", "inertial")):
    def f():
        try:
            tree = ET.parse(sdf_file)
            root = tree.getroot()
            missing = [tag for tag in required_tags if not root.findall(f".//{tag}")]
            if not missing:
                return True, "All required tags are present", None
            else:
                return False, f"Missing tags: {', '.join(missing)}", None
        except ET.ParseError as e:
            if hasattr(e, "position"):
                line, col = e.position
                msg = f"XML Parse Error: {e}"
                return False, f"{msg} at line {line}, col {col}", (msg, line, col)
            else:
                msg = f"XML Parse Error: {e}"
                return False, msg, (msg, 0, 0)

    return f


def test_model_tag_exists(sdf_file):
    def f():
        try:
            tree = ET.parse(sdf_file)
            models = tree.getroot().findall(".//model")
            if models:
                return True, f"Found {len(models)} <model> tags", None
            return False, "No <model> tag found", None
        except ET.ParseError as e:
            if hasattr(e, "position"):
                line, col = e.position
                msg = f"XML Parse Error: {e}"
                return False, f"{msg} at line {line}, col {col}", (msg, line, col)
            else:
                msg = f"XML Parse Error: {e}"
                return False, msg, (msg, 0, 0)

    return f


def test_model_has_name(sdf_file):
    def f():
        try:
            tree = ET.parse(sdf_file)
            ok, missing = 0, 0
            for elem in tree.getroot().findall(".//model"):
                if "name" in elem.attrib and elem.attrib["name"]:
                    ok += 1
                else:
                    missing += 1
            if missing == 0:
                return True, f"All models have 'name' attribute ({ok} found)", None
            else:
                return False, f"{missing} model(s) missing 'name' attribute", None
        except ET.ParseError as e:
            if hasattr(e, "position"):
                line, col = e.position
                msg = f"XML Parse Error: {e}"
                return False, f"{msg} at line {line}, col {col}", (msg, line, col)
            else:
                msg = f"XML Parse Error: {e}"
                return False, msg, (msg, 0, 0)

    return f


def test_unique_model_names(sdf_file):
    def f():
        try:
            tree = ET.parse(sdf_file)
            names = set()
            dups = []
            for elem in tree.getroot().findall(".//model"):
                name = elem.attrib.get("name")
                if name in names:
                    dups.append(name)
                else:
                    names.add(name)
            if not dups:
                return True, "All model names unique", None
            else:
                return False, f"Duplicate model names: {', '.join(dups)}", None
        except ET.ParseError as e:
            if hasattr(e, "position"):
                line, col = e.position
                msg = f"XML Parse Error: {e}"
                return False, f"{msg} at line {line}, col {col}", (msg, line, col)
            else:
                msg = f"XML Parse Error: {e}"
                return False, msg, (msg, 0, 0)

    return f


def test_link_tag_inside_model(sdf_file):
    """Ensure every <link> is a descendant of some <model>."""

    def f():
        try:
            tree = ET.parse(sdf_file)
            root = tree.getroot()
            total_links = len(root.findall(".//link"))
            links_in_models = len(root.findall(".//model//link"))
            if total_links == links_in_models:
                return True, "All <link> tags are inside <model>", None
            else:
                outside = total_links - links_in_models
                return False, f"{outside} <link>(s) found outside any <model>", None
        except ET.ParseError as e:
            if hasattr(e, "position"):
                line, col = e.position
                msg = f"XML Parse Error: {e}"
                return False, f"{msg} at line {line}, col {col}", (msg, line, col)
            else:
                msg = f"XML Parse Error: {e}"
                return False, msg, (msg, 0, 0)

    return f


def test_empty_pose_tags(sdf_file):
    def f():
        try:
            tree = ET.parse(sdf_file)
            empty = [
                p
                for p in tree.getroot().findall(".//pose")
                if not (p.text and p.text.strip())
            ]
            if not empty:
                return True, "No empty <pose> tags", None
            else:
                return False, f"{len(empty)} empty <pose> tag(s) found", None
        except ET.ParseError as e:
            if hasattr(e, "position"):
                line, col = e.position
                msg = f"XML Parse Error: {e}"
                return False, f"{msg} at line {line}, col {col}", (msg, line, col)
            else:
                msg = f"XML Parse Error: {e}"
                return False, msg, (msg, 0, 0)

    return f


def test_deprecated_tags(sdf_file, deprecated_tags=("geometry_old", "old_tag")):
    def f():
        try:
            tree = ET.parse(sdf_file)
            found = [
                elem.tag
                for elem in tree.getroot().iter()
                if elem.tag in deprecated_tags
            ]
            if not found:
                return True, "No deprecated tags found", None
            else:
                return False, f"Deprecated tags used: {', '.join(found)}", None
        except ET.ParseError as e:
            if hasattr(e, "position"):
                line, col = e.position
                msg = f"XML Parse Error: {e}"
                return False, f"{msg} at line {line}, col {col}", (msg, line, col)
            else:
                msg = f"XML Parse Error: {e}"
                return False, msg, (msg, 0, 0)

    return f


def test_namespace_usage(sdf_file):
    def f():
        try:
            tree = ET.parse(sdf_file)
            found = set()
            for elem in tree.getroot().iter():
                if elem.tag.startswith("{"):
                    found.add(elem.tag.split("}")[0][1:])
            if found:
                return True, f"Namespaces detected: {', '.join(sorted(found))}", None
            else:
                return True, "No XML namespaces detected", None
        except ET.ParseError as e:
            if hasattr(e, "position"):
                line, col = e.position
                msg = f"XML Parse Error: {e}"
                return False, f"{msg} at line {line}, col {col}", (msg, line, col)
            else:
                msg = f"XML Parse Error: {e}"
                return False, msg, (msg, 0, 0)

    return f


def test_file_exists(sdf_file):
    def f():
        if os.path.exists(sdf_file):
            return True, "File exists", None
        else:
            return False, f"File not found at {sdf_file}", None

    return f


def test_sdf_root(sdf_file):
    def f():
        try:
            tree = ET.parse(sdf_file)
            root = tree.getroot()
            if root.tag == "sdf":
                return True, "<sdf> root element found", None
            else:
                return False, f"Root element is <{root.tag}> instead of <sdf>", None
        except ET.ParseError as e:
            if hasattr(e, "position"):
                line, col = e.position
                msg = f"XML Parse Error: {e}"
                return False, f"{msg} at line {line}, col {col}", (msg, line, col)
            else:
                msg = f"XML Parse Error: {e}"
                return False, msg, (msg, 0, 0)

    return f


def test_content_looks_like_xml(sdf_file):
    def f():
        try:
            with open(sdf_file, "r", encoding="utf-8") as fobj:
                content = fobj.read()
            if not content.strip():
                return False, "File is empty", None
            if not content.lstrip().startswith("<"):
                sample = content.strip()[:30]
                return (
                    False,
                    f"File does not appear to be XML. Starts with: '{sample}'",
                    None,
                )
            return True, "File content looks like XML", None
        except Exception as e:
            return False, f"Exception reading file: {e}", None

    return f


def test_sdf_version(sdf_file):
    def f():
        try:
            tree = ET.parse(sdf_file)
            root = tree.getroot()
            sdf_version = root.attrib.get("version", None)
            if sdf_version:
                return True, f"SDF version: {sdf_version}", None
            else:
                return False, "No SDF version attribute found", None
        except ET.ParseError as e:
            if hasattr(e, "position"):
                line, col = e.position
                msg = f"XML Parse Error: {e}"
                return False, f"{msg} at line {line}, col {col}", (msg, line, col)
            else:
                msg = f"XML Parse Error: {e}"
                return False, msg, (msg, 0, 0)

    return f


def test_model_or_world_present(sdf_file):
    def f():
        try:
            tree = ET.parse(sdf_file)
            root = tree.getroot()
            if root.find("model") is not None or root.find("world") is not None:
                return True, "<model> or <world> element found", None
            else:
                return False, "Neither <model> nor <world> found", None
        except ET.ParseError as e:
            if hasattr(e, "position"):
                line, col = e.position
                msg = f"XML Parse Error: {e}"
                return False, f"{msg} at line {line}, col {col}", (msg, line, col)
            else:
                msg = f"XML Parse Error: {e}"
                return False, msg, (msg, 0, 0)

    return f


def test_sdf_extension(sdf_file):
    def f():
        if not sdf_file.lower().endswith(".sdf"):
            return False, "File extension is not .sdf", None
        return True, "File extension is .sdf", None

    return f


def test_xmllint_well_formed(sdf_file):
    def f():
        try:
            if shutil.which("xmllint") is None:
                return (
                    False,
                    (
                        "xmllint not found on PATH. Install it "
                        "(e.g. Debian/Ubuntu: `sudo apt-get install libxml2-utils`, "
                        "macOS Homebrew: `brew install libxml2` and ensure it’s linked)."
                    ),
                    None,
                )
            proc = subprocess.run(
                ["xmllint", "--noout", sdf_file], capture_output=True, text=True
            )
            if proc.returncode == 0:
                return True, "xmllint: XML is well-formed", None
            else:
                err = proc.stderr.strip() or "Unknown xmllint error"
                return False, f"xmllint validation failed:\n{err}", None
        except Exception as e:
            return False, f"xmllint invocation error: {e}", None

    return f


def test_xml_pretty_formatting(sdf_file, min_newlines=5):
    def f():
        try:
            with open(sdf_file, "r", encoding="utf-8") as fobj:
                content = fobj.read()

            nl_count = content.count("\n")
            if nl_count < min_newlines:
                return (
                    False,
                    f"XML appears minified (only {nl_count} newline(s)).",
                    None,
                )

            # Look for at least one line starting with 2+ spaces before a tag
            indented = re.search(r"^\s{2,}<", content, flags=re.M) is not None
            if not indented:
                return (
                    False,
                    "No indented element lines found; indentation may be missing.",
                    None,
                )

            return True, f"XML has {nl_count} newline(s) and shows indentation.", None
        except Exception as e:
            return False, f"Exception reading file: {e}", None

    return f


def test_obj_png_path_resolution(sdf_file):
    def f():
        try:
            tree = ET.parse(sdf_file)
            root = tree.getroot()
            uri_elements = root.findall(".//uri")

            base_dir = os.path.dirname(sdf_file)
            seen_uris = set()
            suggestions = []
            missing = []

            for uri_elem in uri_elements:
                uri_text = uri_elem.text.strip() if uri_elem.text else ""
                if uri_text in seen_uris:
                    continue  # Skip duplicate URIs
                seen_uris.add(uri_text)

                if not uri_text.lower().endswith((".obj", ".png")):
                    continue

                filename = os.path.basename(uri_text)
                ext = os.path.splitext(filename)[1].lower()
                subdir = (
                    "meshes" if ext == ".obj" else os.path.join("materials", "textures")
                )
                expected_path = os.path.join(base_dir, subdir, filename)

                if os.path.exists(expected_path):
                    correct_rel_path = os.path.join(subdir, filename).replace("\\", "/")
                    if uri_text != correct_rel_path:
                        suggestions.append(
                            f"- `{uri_text}` → Change to: `{correct_rel_path}`"
                        )
                    continue

                fallback_path = os.path.join(base_dir, filename)
                if os.path.exists(fallback_path):
                    if uri_text != filename:
                        suggestions.append(
                            f"- `{uri_text}` → Change to: `{filename}` (found in root dir)"
                        )
                else:
                    missing.append(
                        f"- `{uri_text}` → File not found in expected locations."
                    )

            if suggestions:
                msg = "\nPath suggestions:\n" + "\n".join(suggestions)
                if missing:
                    msg += "\n\n⚠️ Missing files:\n" + "\n".join(missing)
                return True, msg, None
            elif missing:
                return False, "Missing files:\n" + "\n".join(missing), None
            else:
                return (
                    True,
                    "All .obj and .png <uri> paths are valid and correctly referenced",
                    None,
                )

        except ET.ParseError as e:
            msg = f"XML Parse Error: {e}"
            if hasattr(e, "position"):
                line, col = e.position
                return False, f"{msg} at line {line}, col {col}", (msg, line, col)
            return False, msg, (msg, 0, 0)
        except Exception as e:
            return False, f"Exception during path resolution: {e}", None

    return f


def test_texture_included(sdf_file):
    """Ensure that at least one PNG texture is referenced in the SDF.

    If none are found, check materials/textures/ for PNGs and suggest
    one.
    """

    def f():
        try:
            tree = ET.parse(sdf_file)
            root = tree.getroot()
            uri_elements = root.findall(".//uri")

            png_refs = [
                u.text.strip()
                for u in uri_elements
                if u.text and u.text.strip().lower().endswith(".png")
            ]

            if png_refs:
                return True, f"PNG texture(s) referenced: {', '.join(png_refs)}", None

            # No PNG reference in SDF → check materials/textures folder
            base_dir = os.path.dirname(sdf_file)
            textures_dir = os.path.join(base_dir, "materials", "textures")
            if os.path.isdir(textures_dir):
                png_files = [
                    f for f in os.listdir(textures_dir) if f.lower().endswith(".png")
                ]
                if png_files:
                    suggestions = "\n".join(
                        f"- {os.path.join('materials', 'textures', f)}"
                        for f in png_files
                    )
                    return (
                        False,
                        (
                            "⚠️ Texture (PNG file) not referenced in SDF❌. include texture : "
                            + suggestions
                        ),
                        None,
                    )
                else:
                    return (
                        False,
                        "No PNG textures found in SDF or in materials/textures directory",
                        None,
                    )
            else:
                return (
                    False,
                    "No <uri> referencing PNG and no materials/textures directory found",
                    None,
                )

        except ET.ParseError as e:
            msg = f"XML Parse Error: {e}"
            if hasattr(e, "position"):
                line, col = e.position
                return False, f"{msg} at line {line}, col {col}", (msg, line, col)
            return False, msg, (msg, 0, 0)
        except Exception as e:
            return False, f"Exception during texture check: {e}", None

    return f


def validate_sdf_with_report(
    sdf_path, *, return_markdown=True, save_markdown_path=None
):
    """Validate an SDF file and return either Markdown or plain-text report.

    Optionally save the Markdown report to `save_markdown_path`.
    """

    def _maybe_save(md):
        if save_markdown_path:
            with open(save_markdown_path, "w", encoding="utf-8") as f:
                f.write(md)

    report = SDFTestReport(sdf_path)
    # Early checks
    report.add_test(test_sdf_extension(sdf_path), "File extension check")
    report.add_test(test_file_exists(sdf_path), "File exists")
    report.add_test(
        test_content_looks_like_xml(sdf_path), "File content looks like XML"
    )
    report.run_all()

    results_block = "\n".join(report.results)

    # Early exit: wrong extension
    if "❌ File extension check" in results_block:
        text = results_block + "\n\nOnly SDF files (.sdf) can be tested by this tool."
        if return_markdown:
            md = [
                "# SDF Test Report",
                "## Results",
                *(f"- {r}" for r in report.results),
                "",
                "> Only SDF files (`.sdf`) can be tested by this tool.",
            ]
            md = "\n".join(md)
            _maybe_save(md)
            return md
        return text

    # Early exit: not XML-ish
    if any("❌" in line for line in report.results[:3]):  # first 3 tests only
        text = (
            results_block
            + "\n\nFile does not appear to be valid XML. Please regenerate the SDF using the Translator_SDF Agent."
        )
        if return_markdown:
            md = [
                "# SDF Test Report",
                "## Results",
                *(f"- {r}" for r in report.results),
                "",
                "> File does not appear to be valid XML. Please regenerate the SDF using the **Translator_SDF** Agent.",
            ]
            md = "\n".join(md)
            _maybe_save(md)
            return md
        return text

    # Full suite
    report.add_test(test_xml_well_formed(sdf_path), "XML well-formed")
    report.add_test(test_sdf_root(sdf_path), "<sdf> root element")
    report.add_test(test_sdf_version(sdf_path), "SDF version attribute")
    report.add_test(test_model_or_world_present(sdf_path), "<model> or <world> present")
    report.add_test(test_required_tags(sdf_path), "Required SDF tags check")
    report.add_test(test_model_tag_exists(sdf_path), "Model tag presence")
    report.add_test(test_model_has_name(sdf_path), "Model name attribute")
    report.add_test(test_unique_model_names(sdf_path), "Unique model names")
    report.add_test(test_link_tag_inside_model(sdf_path), "<link> inside <model>")
    report.add_test(test_empty_pose_tags(sdf_path), "Empty <pose> tags")
    report.add_test(test_deprecated_tags(sdf_path), "Deprecated tag usage")
    report.add_test(test_namespace_usage(sdf_path), "Namespace usage")
    report.add_test(test_xmllint_well_formed(sdf_path), "xmllint well-formed check")
    report.add_test(test_xml_pretty_formatting(sdf_path), "XML pretty formatting")
    report.add_test(test_obj_png_path_resolution(sdf_path), "OBJ/PNG path resolution")
    # report.add_test(test_texture_included(sdf_path), "Texture inclusion check")
    report.run_all()

    if return_markdown:
        md = report.report_markdown()
        _maybe_save(md)
        return md

    return report.report()


if __name__ == "__main__":
    sdf_file = "data/mjcf/apartment/model.sdf"
    # Returns Markdown and also saves it alongside the SDF:
    md_path = os.path.join(os.path.dirname(sdf_file), "sdf_test_report.md")
    md = validate_sdf_with_report(
        sdf_file, return_markdown=True, save_markdown_path=md_path
    )
    print(md)
