import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET


class URDFTestReport:
    def __init__(self, urdf_file):
        self.urdf_file = urdf_file
        self.tests = []
        self.results = []
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
            context = get_context_lines(self.urdf_file, line)
            output += (
                f"\n\nFirst XML Parse Error:\n{msg} at line {line}, col {col}\n"
                f"Context:\n{context}"
            )
        return output

    def report_markdown(self):
        """Return the report as Markdown (good for GUI rendering)."""
        lines = []
        lines.append("# URDF Test Report")
        lines.append(f"**File:** `{self.urdf_file}`\n")
        lines.append("## Results")
        for r in self.results:
            lines.append(f"- {r}")

        if self.first_parse_error:
            msg, line, col = self.first_parse_error
            context = get_context_lines(self.urdf_file, line)
            lines.append("\n## First XML Parse Error")
            lines.append(f"- **Message:** `{msg}`")
            lines.append(f"- **Location:** line **{line}**, col **{col}**")
            lines.append("\n**Context:**")
            lines.append("```xml")
            lines.append(context.rstrip("\n"))
            lines.append("```")

        return "\n".join(lines)


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


# ----- TEST FUNCTIONS -----
# All test functions return (result, message, parse_error)
# parse_error: (msg, line, col) or None


def test_file_exists(urdf_file):
    def f():
        if os.path.exists(urdf_file):
            return True, "File exists", None
        else:
            return False, f"File not found: {urdf_file}", None

    return f


def test_xml_well_formed(urdf_file):
    def f():
        try:
            ET.parse(urdf_file)
            return True, "XML is well-formed", None
        except ET.ParseError as e:
            line, col = getattr(e, "position", (0, 0))
            msg = f"XML Parse Error: {e}"
            return False, f"{msg} at line {line}, col {col}", (msg, line, col)

    return f


def test_robot_root(urdf_file):
    def f():
        try:
            tree = ET.parse(urdf_file)
            root = tree.getroot()
            if root.tag == "robot":
                return True, "<robot> root element found", None
            else:
                return False, f"Root element is <{root.tag}> instead of <robot>", None
        except ET.ParseError as e:
            line, col = getattr(e, "position", (0, 0))
            msg = f"XML Parse Error: {e}"
            return False, f"{msg} at line {line}, col {col}", (msg, line, col)

    return f


def test_robot_name_attribute(urdf_file):
    def f():
        try:
            tree = ET.parse(urdf_file)
            root = tree.getroot()
            name = root.attrib.get("name", None)
            if name:
                return True, f"Robot name: {name}", None
            else:
                return False, "No 'name' attribute in <robot> element", None
        except ET.ParseError as e:
            line, col = getattr(e, "position", (0, 0))
            msg = f"XML Parse Error: {e}"
            return False, f"{msg} at line {line}, col {col}", (msg, line, col)

    return f


def test_required_tags(urdf_file, required_tags=("link", "joint")):
    def f():
        try:
            tree = ET.parse(urdf_file)
            root = tree.getroot()
            missing = [tag for tag in required_tags if not root.findall(f".//{tag}")]
            if not missing:
                return True, "All required tags present", None
            else:
                return False, f"Missing required tag(s): {', '.join(missing)}", None
        except ET.ParseError as e:
            line, col = getattr(e, "position", (0, 0))
            msg = f"XML Parse Error: {e}"
            return False, f"{msg} at line {line}, col {col}", (msg, line, col)

    return f


def test_unique_link_names(urdf_file):
    def f():
        try:
            tree = ET.parse(urdf_file)
            names = set()
            dups = []
            for link in tree.getroot().findall(".//link"):
                name = link.attrib.get("name")
                if name in names:
                    dups.append(name)
                else:
                    names.add(name)
            if not dups:
                return True, "All <link> names are unique", None
            else:
                return False, f"Duplicate <link> names: {', '.join(dups)}", None
        except ET.ParseError as e:
            line, col = getattr(e, "position", (0, 0))
            msg = f"XML Parse Error: {e}"
            return False, f"{msg} at line {line}, col {col}", (msg, line, col)

    return f


def test_unique_joint_names(urdf_file):
    def f():
        try:
            tree = ET.parse(urdf_file)
            names = set()
            dups = []
            for joint in tree.getroot().findall(".//joint"):
                name = joint.attrib.get("name")
                if name in names:
                    dups.append(name)
                else:
                    names.add(name)
            if not dups:
                return True, "All <joint> names are unique", None
            else:
                return False, f"Duplicate <joint> names: {', '.join(dups)}", None
        except ET.ParseError as e:
            line, col = getattr(e, "position", (0, 0))
            msg = f"XML Parse Error: {e}"
            return False, f"{msg} at line {line}, col {col}", (msg, line, col)

    return f


def test_deprecated_tags(urdf_file, deprecated_tags=("calibration", "mimic")):
    def f():
        try:
            tree = ET.parse(urdf_file)
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
            line, col = getattr(e, "position", (0, 0))
            msg = f"XML Parse Error: {e}"
            return False, f"{msg} at line {line}, col {col}", (msg, line, col)

    return f


def test_links_have_inertial(urdf_file):
    def f():
        try:
            tree = ET.parse(urdf_file)
            missing = []
            for link in tree.getroot().findall(".//link"):
                name = link.attrib.get("name", "<unnamed>")
                if name.lower() != "world" and link.find("inertial") is None:
                    missing.append(name)
            if not missing:
                return True, "All non-world <link> elements have <inertial>", None
            else:
                return False, f"Links missing <inertial>: {', '.join(missing)}", None
        except ET.ParseError as e:
            line, col = getattr(e, "position", (0, 0))
            msg = f"XML Parse Error: {e}"
            return False, f"{msg} at line {line}, col {col}", (msg, line, col)

    return f


def test_content_looks_like_xml(urdf_file):
    def f():
        try:
            with open(urdf_file, "r", encoding="utf-8") as fobj:
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


def test_urdf_extension(urdf_file):
    def f():
        if not urdf_file.lower().endswith(".urdf"):
            return False, "File extension is not .urdf", None
        return True, "File extension is .urdf", None

    return f


def test_xmllint_well_formed(urdf_file):
    """Validate with xmllint --noout (if available)."""

    def f():
        try:
            if shutil.which("xmllint") is None:
                return (
                    False,
                    (
                        "xmllint not found on PATH. Install it "
                        "(Debian/Ubuntu: 'sudo apt-get install libxml2-utils', "
                        "macOS (brew): 'brew install libxml2')."
                    ),
                    None,
                )
            proc = subprocess.run(
                ["xmllint", "--noout", urdf_file], capture_output=True, text=True
            )
            if proc.returncode == 0:
                return True, "xmllint: XML is well-formed", None
            else:
                err = proc.stderr.strip() or "Unknown xmllint error"
                return False, f"xmllint validation failed:\n{err}", None
        except Exception as e:
            return False, f"xmllint invocation error: {e}", None

    return f


def test_xml_pretty_formatting(urdf_file, min_newlines=5):
    """Heuristic check: ensure multiple lines and some indentation."""

    def f():
        try:
            with open(urdf_file, "r", encoding="utf-8") as fobj:
                content = fobj.read()

            nl_count = content.count("\n")
            if nl_count < min_newlines:
                return (
                    False,
                    f"XML appears minified (only {nl_count} newline(s)).",
                    None,
                )

            # Look for at least one line starting with 2+ spaces before a tag
            if re.search(r"^\s{2,}<", content, flags=re.M) is None:
                return (
                    False,
                    "No indented element lines found; indentation may be missing.",
                    None,
                )

            return True, f"XML has {nl_count} newline(s) and shows indentation.", None
        except Exception as e:
            return False, f"Exception reading file: {e}", None

    return f


def validate_urdf_with_report(
    urdf_path, *, return_markdown=True, save_markdown_path=None
):
    """Validate a URDF file and return either Markdown or plain-text report.

    Optionally save the Markdown report to `save_markdown_path`.
    """

    def _maybe_save(md):
        if save_markdown_path:
            with open(save_markdown_path, "w", encoding="utf-8") as f:
                f.write(md)

    report = URDFTestReport(urdf_path)
    report.add_test(test_urdf_extension(urdf_path), "File extension check")
    report.add_test(test_file_exists(urdf_path), "File exists")
    report.add_test(
        test_content_looks_like_xml(urdf_path), "File content looks like XML"
    )
    report.run_all()

    results_block = "\n".join(report.results)

    # Early exit: wrong extension
    if "❌ File extension check" in results_block:
        text = results_block + "\n\nOnly URDF files (.urdf) can be tested by this tool."
        if return_markdown:
            md = [
                "# URDF Test Report",
                "## Results",
                *(f"- {r}" for r in report.results),
                "",
                "> Only URDF files (`.urdf`) can be tested by this tool.",
            ]
            md = "\n".join(md)
            _maybe_save(md)
            return md
        return text

    # Early exit: not XML-ish
    if any("❌" in line for line in report.results[:3]):
        text = (
            results_block
            + "\n\nFile does not appear to be valid XML. Please regenerate the URDF using the Translator_URDF Agent."
        )
        if return_markdown:
            md = [
                "# URDF Test Report",
                "## Results",
                *(f"- {r}" for r in report.results),
                "",
                "> File does not appear to be valid XML. Please regenerate the URDF using the **Translator_URDF** Agent.",
            ]
            md = "\n".join(md)
            _maybe_save(md)
            return md
        return text

    # Proceed with full suite
    report.add_test(test_xml_well_formed(urdf_path), "XML well-formed")
    report.add_test(test_robot_root(urdf_path), "<robot> root element")
    report.add_test(test_robot_name_attribute(urdf_path), "<robot> name attribute")
    report.add_test(test_required_tags(urdf_path), "Required tags check")
    report.add_test(test_unique_link_names(urdf_path), "Unique <link> names")
    report.add_test(test_unique_joint_names(urdf_path), "Unique <joint> names")
    report.add_test(test_links_have_inertial(urdf_path), "Links have <inertial>")
    report.add_test(test_deprecated_tags(urdf_path), "Deprecated tags usage")
    report.add_test(test_xmllint_well_formed(urdf_path), "xmllint well-formed check")
    report.add_test(test_xml_pretty_formatting(urdf_path), "XML pretty formatting")
    report.run_all()

    if return_markdown:
        md = report.report_markdown()
        _maybe_save(md)
        return md

    return report.report()


if __name__ == "__main__":
    urdf_file = "data/urdf/output.urdf"
    # Returns Markdown and also saves it alongside the URDF:
    md_path = os.path.join(os.path.dirname(urdf_file), "urdf_test_report.md")
    md = validate_urdf_with_report(
        urdf_file, return_markdown=True, save_markdown_path=md_path
    )
    print(md)
