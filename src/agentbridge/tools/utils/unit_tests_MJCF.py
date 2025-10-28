import os
import re
import xml.etree.ElementTree as ET


class MJCFTestReport:
    """Utility to organize, run, and report validation tests for MJCF files."""

    def __init__(self, mjcf_file):
        self.mjcf_file = mjcf_file
        self.tests = []              # List of (function, description)
        self.results = []            # Collected results after running tests
        self.mjcf_root = None        # Cached XML root node
        self.first_parse_error = None  # Store first encountered parse error (msg, line, col)

    def add_test(self, func, description):
        """Register a test function with a description."""
        self.tests.append((func, description))

    def run_all(self):
        """Execute all registered tests and store results."""
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
        """Return a plain-text validation report."""
        output = "\n".join(self.results)
        if self.first_parse_error:
            msg, line, col = self.first_parse_error
            context = get_context_lines(self.mjcf_file, line)
            output += f"\n\nFirst XML Parse Error:\n{msg} at line {line}, col {col}\nContext:\n{context}"
        return output

    def report_markdown(self):
        """Return a Markdown-formatted validation report (for saving or displaying)."""
        lines = []
        lines.append("# MJCF Test Report")
        lines.append(f"**File:** `{self.mjcf_file}`\n")
        lines.append("## Results")
        for r in self.results:
            lines.append(f"- {r}")

        if self.first_parse_error:
            msg, line, col = self.first_parse_error
            context = get_context_lines(self.mjcf_file, line)
            lines.append("\n## First XML Parse Error")
            lines.append(f"- **Message:** `{msg}`")
            lines.append(f"- **Location:** line **{line}**, col **{col}**")
            lines.append("\n**Context:**")
            lines.append("```xml")
            lines.append(context.rstrip("\n"))
            lines.append("```")

        return "\n".join(lines)

    def load_root(self):
        """Lazy-load the XML tree root for this MJCF file."""
        if self.mjcf_root is None:
            try:
                tree = ET.parse(self.mjcf_file)
                self.mjcf_root = tree.getroot()
            except Exception:
                self.mjcf_root = None
        return self.mjcf_root


def get_context_lines(file_path, error_line, context=3):
    """Return a few lines of text around an error line for debugging purposes."""
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
# Each function returns a closure `f()` that runs the actual test when called.


def test_xml_well_formed(mjcf_file):
    """Check that the XML parses without syntax errors."""
    def f():
        try:
            ET.parse(mjcf_file)
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


def test_mjcf_root(mjcf_file):
    """Verify that the root element is <mujoco>."""
    def f():
        try:
            tree = ET.parse(mjcf_file)
            root = tree.getroot()
            if root.tag == "mujoco":
                return True, "<mujoco> root element found", None
            else:
                return False, f"Root element is <{root.tag}> instead of <mujoco>", None
        except ET.ParseError as e:
            msg = f"XML Parse Error: {e}"
            line, col = getattr(e, "position", (0, 0))
            return False, f"{msg} at line {line}, col {col}", (msg, line, col)
    return f


def test_required_sections(mjcf_file, required=("compiler", "asset", "worldbody")):
    """Check that key MJCF sections (compiler, asset, worldbody) are present."""
    def f():
        try:
            tree = ET.parse(mjcf_file)
            root = tree.getroot()
            missing = [tag for tag in required if not root.findall(f".//{tag}")]
            if not missing:
                return True, "All required sections present", None
            else:
                return False, f"Missing sections: {', '.join(missing)}", None
        except ET.ParseError as e:
            msg = f"XML Parse Error: {e}"
            line, col = getattr(e, "position", (0, 0))
            return False, f"{msg} at line {line}, col {col}", (msg, line, col)
    return f


def test_body_tags(mjcf_file):
    """Ensure that <body> tags exist in the file."""
    def f():
        try:
            tree = ET.parse(mjcf_file)
            bodies = tree.getroot().findall(".//body")
            if bodies:
                return True, f"Found {len(bodies)} <body> tags", None
            else:
                return False, "No <body> tags found", None
        except ET.ParseError as e:
            msg = f"XML Parse Error: {e}"
            line, col = getattr(e, "position", (0, 0))
            return False, f"{msg} at line {line}, col {col}", (msg, line, col)
    return f


def test_unique_body_names(mjcf_file):
    """Check that all <body> elements have unique names."""
    def f():
        try:
            tree = ET.parse(mjcf_file)
            names = set()
            dups = []
            for elem in tree.getroot().findall(".//body"):
                name = elem.attrib.get("name")
                if not name:
                    continue
                if name in names:
                    dups.append(name)
                else:
                    names.add(name)
            if not dups:
                return True, "All body names unique", None
            else:
                return False, f"Duplicate body names: {', '.join(dups)}", None
        except ET.ParseError as e:
            msg = f"XML Parse Error: {e}"
            line, col = getattr(e, "position", (0, 0))
            return False, f"{msg} at line {line}, col {col}", (msg, line, col)
    return f


def test_geom_types(mjcf_file, allowed=("box", "sphere", "cylinder", "mesh", "plane", "capsule")):
    """Verify that <geom> elements use only supported types."""
    def f():
        try:
            tree = ET.parse(mjcf_file)
            bad = []
            for elem in tree.getroot().findall(".//geom"):
                gtype = elem.attrib.get("type")
                if gtype and gtype not in allowed:
                    bad.append(gtype)
            if not bad:
                return True, "All geom types valid", None
            else:
                return False, f"Unsupported geom types: {', '.join(set(bad))}", None
        except ET.ParseError as e:
            msg = f"XML Parse Error: {e}"
            line, col = getattr(e, "position", (0, 0))
            return False, f"{msg} at line {line}, col {col}", (msg, line, col)
    return f


def test_inertial_mass(mjcf_file):
    """Check that all <inertial> mass attributes are positive floats."""
    def f():
        try:
            tree = ET.parse(mjcf_file)
            bad = []
            for elem in tree.getroot().findall(".//inertial"):
                mass = elem.attrib.get("mass")
                if mass and float(mass) <= 0:
                    bad.append(mass)
            if not bad:
                return True, "All inertial masses positive", None
            else:
                return False, f"Invalid (non-positive) masses: {', '.join(bad)}", None
        except ET.ParseError as e:
            msg = f"XML Parse Error: {e}"
            line, col = getattr(e, "position", (0, 0))
            return False, f"{msg} at line {line}, col {col}", (msg, line, col)
        except ValueError as ve:
            return False, f"Invalid mass attribute value: {ve}", None
    return f


def test_file_exists(mjcf_file):
    """Verify that the file physically exists on disk."""
    def f():
        if os.path.exists(mjcf_file):
            return True, "File exists", None
        else:
            return False, f"File not found at {mjcf_file}", None
    return f


def test_xml_pretty_formatting(mjcf_file, min_newlines=5):
    """Check whether XML looks human-readable (not minified)."""
    def f():
        try:
            with open(mjcf_file, "r", encoding="utf-8") as fobj:
                content = fobj.read()

            nl_count = content.count("\n")
            if nl_count < min_newlines:
                return False, f"XML appears minified (only {nl_count} newline(s)).", None

            indented = re.search(r"^\s{2,}<", content, flags=re.M) is not None
            if not indented:
                return False, "No indented element lines found; indentation may be missing.", None

            return True, f"XML has {nl_count} newline(s) and shows indentation.", None
        except Exception as e:
            return False, f"Exception reading file: {e}", None
    return f


def test_unique_geom_names(mjcf_file):
    """Check that all <geom> names are unique (no duplicates)."""
    def f():
        try:
            tree = ET.parse(mjcf_file)
            geoms = tree.getroot().findall(".//geom")
            names = set()
            dups = []
            for g in geoms:
                name = g.attrib.get("name")
                if not name:
                    continue
                if name in names:
                    dups.append(name)
                else:
                    names.add(name)
            if not dups:
                return True, "All geom names unique", None
            else:
                return False, f"Duplicate geom names: {', '.join(dups)}", None
        except ET.ParseError as e:
            msg = f"XML Parse Error: {e}"
            line, col = getattr(e, "position", (0, 0))
            return False, f"{msg} at line {line}, col {col}", (msg, line, col)
    return f


def test_unused_assets(mjcf_file):
    """Check whether declared assets (materials, textures, meshes) are actually used."""
    def f():
        try:
            tree = ET.parse(mjcf_file)
            root = tree.getroot()

            declared_materials = {m.attrib["name"] for m in root.findall(".//material") if "name" in m.attrib}
            declared_textures = {t.attrib["name"] for t in root.findall(".//texture") if "name" in t.attrib}
            declared_meshes = {m.attrib["name"] for m in root.findall(".//mesh") if "name" in m.attrib}

            used_materials = {g.attrib["material"] for g in root.findall(".//geom") if "material" in g.attrib}
            used_textures = {m.attrib["texture"] for m in root.findall(".//material") if "texture" in m.attrib}
            used_meshes = {g.attrib["mesh"] for g in root.findall(".//geom") if "mesh" in g.attrib}

            unused_mats = declared_materials - used_materials
            unused_texs = declared_textures - used_textures
            unused_mesh = declared_meshes - used_meshes

            if not (unused_mats or unused_texs or unused_mesh):
                return True, "All declared assets are used", None
            else:
                problems = []
                if unused_mats:
                    problems.append(f"Unused materials: {', '.join(unused_mats)}")
                if unused_texs:
                    problems.append(f"Unused textures: {', '.join(unused_texs)}")
                if unused_mesh:
                    problems.append(f"Unused meshes: {', '.join(unused_mesh)}")
                return False, "; ".join(problems), None
        except ET.ParseError as e:
            msg = f"XML Parse Error: {e}"
            line, col = getattr(e, "position", (0, 0))
            return False, f"{msg} at line {line}, col {col}", (msg, line, col)
    return f


def validate_mjcf_with_report(mjcf_path, *, return_markdown=True, save_markdown_path=None):
    """Run the full suite of MJCF validation checks and return a report."""
    def _maybe_save(md):
        if save_markdown_path:
            with open(save_markdown_path, "w", encoding="utf-8") as f:
                f.write(md)

    report = MJCFTestReport(mjcf_path)
    # Register tests in sequence
    report.add_test(test_file_exists(mjcf_path), "File exists")
    report.add_test(test_xml_well_formed(mjcf_path), "XML well-formed")
    report.add_test(test_mjcf_root(mjcf_path), "<mujoco> root element")
    report.add_test(test_required_sections(mjcf_path), "Required sections present")
    report.add_test(test_body_tags(mjcf_path), "Body tag presence")
    report.add_test(test_unique_body_names(mjcf_path), "Unique body names")
    report.add_test(test_geom_types(mjcf_path), "Geom type validity")
    report.add_test(test_inertial_mass(mjcf_path), "Positive inertial mass")
    report.add_test(test_xml_pretty_formatting(mjcf_path), "XML formatting check")
    report.add_test(test_unique_geom_names(mjcf_path), "Unique geom names")
    report.add_test(test_unused_assets(mjcf_path), "Unused assets check")
    report.run_all()

    if return_markdown:
        md = report.report_markdown()
        _maybe_save(md)
        return md
    return report.report()


if __name__ == "__main__":
    mjcf_file = "data/mjcf/cone.xml"
    md_path = os.path.join(os.path.dirname(mjcf_file), "mjcf_test_report.md")
    md = validate_mjcf_with_report(mjcf_file, return_markdown=True, save_markdown_path=md_path)
    print(md)
