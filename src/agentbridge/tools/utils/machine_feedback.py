import os
import shutil
import subprocess
import xml.etree.ElementTree as ET


def check_gz_installed():
    """Check if the Gazebo (`gz`) CLI is installed and accessible.

    First tries PATH, then sources ROS Jazzy environment to locate it.
    Returns a tuple (ok, message).
    """
    if shutil.which("gz"):
        return True, "✅ Gazebo (gz) is installed"
    cmd = "source /opt/ros/jazzy/setup.bash && which gz"
    try:
        result = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)
        if result.stdout.strip():
            return True, "✅ Gazebo found after sourcing ROS Jazzy"
        return False, (
            "Gazebo (gz) CLI tool not found.\n\n"
            "Tried sourcing ROS Jazzy environment, but `gz` is still unavailable.\n\n"
            "❌ Gazebo-based validation and simulation tests cannot be performed.\n"
        )
    except Exception as e:
        return False, f"❌ Error checking Gazebo: {e}"


def check_file_extension(file_path):
    """Ensure the given file exists and has either .sdf or .urdf extension."""
    if not os.path.exists(file_path):
        return False, "❌ File does not exist", None
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in [".sdf", ".urdf"]:
        return False, "❌ File extension must be .sdf or .urdf", None
    return True, f"✅ File extension is valid ({ext})", ext


def test_xml_well_formed(file_path):
    """Quick XML well-formedness check using ElementTree."""
    try:
        ET.parse(file_path)
        return True, "✅ XML is well-formed", None
    except ET.ParseError as e:
        msg = f"❌ XML Parse Error: {e}"
        if hasattr(e, "position"):
            line, col = e.position
            return False, f"{msg} at line {line}, col {col}", (msg, line, col)
        return False, msg, (msg, 0, 0)


def convert_urdf_to_sdf(urdf_file):
    """Convert a URDF file into SDF format using `gz sdf -p`.

    Stores the result as `converted_model.sdf` next to the URDF.
    """
    try:
        sdf_file = os.path.join(os.path.dirname(urdf_file), "converted_model.sdf")
        cmd = f"source /opt/ros/jazzy/setup.bash && gz sdf -p {urdf_file}"
        with open(sdf_file, "w") as f:
            subprocess.run(
                ["bash", "-c", cmd],
                stdout=f,
                stderr=subprocess.PIPE,
                check=True,
                text=True,
            )
        return True, f"✅ URDF converted to {sdf_file}", sdf_file
    except subprocess.CalledProcessError as e:
        return False, f"❌ URDF conversion failed: {e.stderr.strip()}", None


def check_sdf_valid(sdf_file):
    """Validate an SDF file using `gz sdf -k`."""
    try:
        cmd = f"source /opt/ros/jazzy/setup.bash && gz sdf -k {sdf_file}"
        result = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)
        if result.returncode == 0 and "Valid" in result.stdout:
            return True, "✅ SDF syntax is valid"
        return (
            False,
            f"❌ Invalid SDF syntax:\n{result.stdout.strip() or result.stderr.strip()}",
        )
    except Exception as e:
        return False, f"❌ Exception during sdf validation: {e}"


def try_gz_sim_launch(sdf_file):
    """Attempt to launch a Gazebo simulation headlessly to verify runtime validity.

    Checks for mesh/URI resolution issues and simulation startup success.
    """
    try:
        cmd = f"source /opt/ros/jazzy/setup.bash && gz sim -r --headless-rendering {sdf_file}"
        result = subprocess.run(
            ["bash", "-c", cmd], capture_output=True, text=True, timeout=20
        )

        if "could not be resolved" in result.stderr or "[Err]" in result.stderr:
            return (
                False,
                f"❌ Mesh/URI resolution error:\n```\n{result.stderr.strip()}\n```",
            )

        if result.returncode == 0:
            return True, "✅ Gazebo simulation started successfully"

        return (
            False,
            f"❌ Gazebo sim returned non-zero:\n```\n{result.stderr.strip()}\n```",
        )
    except subprocess.TimeoutExpired:
        return False, "❌ Gazebo sim timed out or crashed"
    except Exception as e:
        return False, f"❌ Error running Gazebo sim: {e}"


def generate_debug_report(file_path):
    """Generate a markdown-formatted debug report for a given .sdf or .urdf file.

    Steps:
      1. Verify Gazebo CLI is available
      2. Check file extension
      3. Validate XML structure
      4. Convert URDF → SDF if needed
      5. Validate SDF syntax
      6. Attempt a Gazebo simulation launch

    Returns:
        str: A report including success/failure messages for each step.
    """
    report = ["# Debug Report", f"**File:** `{file_path}`\n"]
    sdf_file = None
    is_urdf = False
    delete_temp_sdf = False

    ok, msg = check_gz_installed()
    report.append(f"- {msg}")
    if not ok:
        return "\n".join(report)

    ok, msg, ext = check_file_extension(file_path)
    report.append(f"- {msg}")
    if not ok:
        return "\n".join(report)

    ok, msg, parse_error = test_xml_well_formed(file_path)
    report.append(f"- {msg}")
    if not ok and parse_error:
        msg, line, col = parse_error
        report.append("\n## XML Error Context")
        report.append(f"- **Message:** `{msg}`")
        report.append(f"- **Location:** line {line}, col {col}")
        return "\n".join(report)

    if ext == ".urdf":
        is_urdf = True
        ok, msg, sdf_file = convert_urdf_to_sdf(file_path)
        report.append(f"- {msg}")
        if not ok:
            return "\n".join(report)
        delete_temp_sdf = True
    else:
        sdf_file = file_path

    ok, sdf_validation_msg = check_sdf_valid(sdf_file)
    report.append(f"- {sdf_validation_msg}")
    if not ok:
        if is_urdf:
            report.append(
                "> ❌ Therefore, URDF is considered **invalid** due to failed SDF conversion."
            )
        return "\n".join(report)

    ok, sim_msg = try_gz_sim_launch(sdf_file)
    report.append(f"- {sim_msg}")
    if not ok:
        if is_urdf:
            report.append(
                "> ❌ Therefore, URDF is considered **invalid** due to failed simulation."
            )
        return "\n".join(report)

    # Clean up temporary SDF if conversion was successful
    if delete_temp_sdf and os.path.exists(sdf_file):
        os.remove(sdf_file)
        report.append(f"- 🧹 Temporary SDF deleted: `{sdf_file}`")

    if is_urdf:
        report.append(
            "\n> ✅ Final Verdict: URDF is **valid** (SDF converted, verified, and simulated successfully)"
        )
    else:
        report.append("\n> ✅ Final Verdict: SDF is **valid** and simulation passed")

    return "\n".join(report)


# Example standalone usage
if __name__ == "__main__":
    file_path = "data/mjcf/ambulance/model.sdf"  # Example target file
    print(generate_debug_report(file_path))
