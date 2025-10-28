import os
import shlex
import shutil
import subprocess
from pathlib import Path
from xml.dom import minidom
from xml.etree import ElementTree as ET


def _copy_tugbot_folder(dest_dir: Path, tugbot_source_dir: str) -> None:
    """Copy the Tugbot model directory into the destination folder.

    The Tugbot model must be available (with `model.config`, `model.sdf`, meshes/, etc.).
    This ensures the spawned world has access to the Tugbot resources.
    """
    source = Path(tugbot_source_dir).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(
            f"Tugbot source folder not found: {source}\n"
            f"Expected contents such as {tugbot_source_dir}/model.config, meshes/, ..."
        )

    target = dest_dir / "Tugbot"
    shutil.copytree(source, target, dirs_exist_ok=True)


def _make_new_path(src_path: Path) -> str:
    """Generate a new filename by appending `_world` before the extension."""
    base, ext = os.path.splitext(str(src_path))
    return f"{base}_world{ext or '.sdf'}"


def _add_prop(parent: ET.Element, key: str, ptype: str, value: str) -> None:
    """Helper to add a <property> child with typed value."""
    ET.SubElement(parent, "property", {"key": key, "type": ptype}).text = value


def _deep_copy(elem: ET.Element) -> ET.Element:
    """Deep copy XML elements while stripping whitespace-only text nodes."""
    new = ET.Element(elem.tag, elem.attrib)
    if elem.text and elem.text.strip():
        new.text = elem.text.strip()
    for child in elem:
        new.append(_deep_copy(child))
    return new


def pretty_print_clean(root: ET.Element) -> str:
    """Return a clean, pretty-printed XML string (no blank whitespace nodes)."""
    rough = ET.tostring(root, encoding="utf-8")
    reparsed = minidom.parseString(rough)
    for node in reparsed.getElementsByTagName("*"):
        for child in list(node.childNodes):
            if child.nodeType == child.TEXT_NODE and not child.data.strip():
                node.removeChild(child)
    return reparsed.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")


def create_sdf_with_agv(
    path: str, tugbot_source_dir: str = "data/resources/Tugbot"
) -> str:
    """Generate a new SDF world that includes the original model plus a Tugbot.

    - If the input already has a <world>, this function injects Tugbot and GUI plugins.
    - If the input is only a <model>, a new <world> wrapper is created.

    Args:
        path: Path to the original model or world SDF file.
        tugbot_source_dir: Path to the Tugbot model folder.

    Returns:
        Path to the new world SDF file (original filename with `_world` suffix).
    """
    src_path = Path(path).expanduser().resolve()
    if not src_path.exists():
        raise FileNotFoundError(f"SDF file not found: {src_path}")

    with src_path.open("r", encoding="utf-8") as f:
        original_sdf = f.read()

    root_in = ET.fromstring(original_sdf)
    if root_in.tag != "sdf":
        raise ValueError("Expected root <sdf> tag.")
    sdf_version = root_in.attrib.get("version", "1.7")

    # If file already defines a <world>, just inject Tugbot and GUI if missing
    model = root_in.find("model")
    if model is None:
        world = root_in.find("world")
        if world is not None:
            print("[DEBUG] Input already has a <world>. Injecting Tugbot and GUI plugins...")

            if world.find("gui") is None:
                gui = ET.SubElement(world, "gui", {"fullscreen": "0"})

                # Teleoperation panel
                teleop = ET.SubElement(gui, "plugin", {"name": "Teleop", "filename": "Teleop"})
                teleop_gui = ET.SubElement(teleop, "ignition-gui")
                _add_prop(teleop_gui, "x", "double", "0")
                _add_prop(teleop_gui, "y", "double", "0")
                _add_prop(teleop_gui, "width", "double", "400")
                _add_prop(teleop_gui, "height", "double", "900")
                _add_prop(teleop_gui, "state", "string", "docked")
                ET.SubElement(teleop, "topic").text = "/model/tugbot/cmd_vel"

                # 3D scene viewer
                scene3d = ET.SubElement(gui, "plugin", {"filename": "GzScene3D", "name": "3D View"})
                scene3d_gui = ET.SubElement(scene3d, "ignition-gui")
                ET.SubElement(scene3d_gui, "title").text = "3D View"
                _add_prop(scene3d_gui, "showTitleBar", "bool", "false")
                _add_prop(scene3d_gui, "state", "string", "docked")
                ET.SubElement(scene3d, "engine").text = "ogre2"
                ET.SubElement(scene3d, "scene").text = "scene"
                ET.SubElement(scene3d, "ambient_light").text = "0.4 0.4 0.4"
                ET.SubElement(scene3d, "background_color").text = "0.8 0.8 0.8"
                ET.SubElement(scene3d, "camera_pose").text = "13.4 -6.1 2.23 0 0.4 -1.83"

                # World control panel
                world_ctrl = ET.SubElement(gui, "plugin", {"filename": "WorldControl", "name": "World control"})
                world_ctrl_gui = ET.SubElement(world_ctrl, "ignition-gui")
                ET.SubElement(world_ctrl_gui, "title").text = "World control"
                _add_prop(world_ctrl_gui, "showTitleBar", "bool", "false")
                _add_prop(world_ctrl_gui, "resizable", "bool", "false")
                _add_prop(world_ctrl_gui, "height", "double", "72")
                _add_prop(world_ctrl_gui, "width", "double", "121")
                _add_prop(world_ctrl_gui, "z", "double", "1")
                _add_prop(world_ctrl_gui, "state", "string", "floating")
                anchors = ET.SubElement(world_ctrl_gui, "anchors", {"target": "3D View"})
                ET.SubElement(anchors, "line", {"own": "left", "target": "left"})
                ET.SubElement(anchors, "line", {"own": "bottom", "target": "bottom"})
                ET.SubElement(world_ctrl, "play_pause").text = "true"
                ET.SubElement(world_ctrl, "step").text = "true"
                ET.SubElement(world_ctrl, "start_paused").text = "true"

            # Add Tugbot include
            include = ET.SubElement(world, "include")
            ET.SubElement(include, "uri").text = "Tugbot"
            ET.SubElement(include, "pose").text = "1 0 0.3 0 0 0"

            new_path = _make_new_path(src_path)
            _copy_tugbot_folder(src_path.parent, tugbot_source_dir)
            with open(new_path, "w", encoding="utf-8") as f:
                f.write(pretty_print_clean(root_in))
            return str(new_path)

    # Otherwise, wrap model inside a new <world>
    sdf_out = ET.Element("sdf", {"version": sdf_version})
    world = ET.SubElement(sdf_out, "world", {"name": "default"})
    ET.SubElement(world, "gravity").text = "0 0 -9.8"

    # GUI plugins as above
    gui = ET.SubElement(world, "gui", {"fullscreen": "0"})
    teleop = ET.SubElement(gui, "plugin", {"name": "Teleop", "filename": "Teleop"})
    teleop_gui = ET.SubElement(teleop, "ignition-gui")
    _add_prop(teleop_gui, "x", "double", "0")
    _add_prop(teleop_gui, "y", "double", "0")
    _add_prop(teleop_gui, "width", "double", "400")
    _add_prop(teleop_gui, "height", "double", "900")
    _add_prop(teleop_gui, "state", "string", "docked")
    ET.SubElement(teleop, "topic").text = "/model/tugbot/cmd_vel"

    scene3d = ET.SubElement(gui, "plugin", {"filename": "GzScene3D", "name": "3D View"})
    scene3d_gui = ET.SubElement(scene3d, "ignition-gui")
    ET.SubElement(scene3d_gui, "title").text = "3D View"
    _add_prop(scene3d_gui, "showTitleBar", "bool", "false")
    _add_prop(scene3d_gui, "state", "string", "docked")
    ET.SubElement(scene3d, "engine").text = "ogre2"
    ET.SubElement(scene3d, "scene").text = "scene"
    ET.SubElement(scene3d, "ambient_light").text = "0.4 0.4 0.4"
    ET.SubElement(scene3d, "background_color").text = "0.8 0.8 0.8"
    ET.SubElement(scene3d, "camera_pose").text = "13.4 -6.1 2.23 0 0.4 -1.83"

    world_ctrl = ET.SubElement(gui, "plugin", {"filename": "WorldControl", "name": "World control"})
    world_ctrl_gui = ET.SubElement(world_ctrl, "ignition-gui")
    ET.SubElement(world_ctrl_gui, "title").text = "World control"
    _add_prop(world_ctrl_gui, "showTitleBar", "bool", "false")
    _add_prop(world_ctrl_gui, "resizable", "bool", "false")
    _add_prop(world_ctrl_gui, "height", "double", "72")
    _add_prop(world_ctrl_gui, "width", "double", "121")
    _add_prop(world_ctrl_gui, "z", "double", "1")
    _add_prop(world_ctrl_gui, "state", "string", "floating")
    anchors = ET.SubElement(world_ctrl_gui, "anchors", {"target": "3D View"})
    ET.SubElement(anchors, "line", {"own": "left", "target": "left"})
    ET.SubElement(anchors, "line", {"own": "bottom", "target": "bottom"})
    ET.SubElement(world_ctrl, "play_pause").text = "true"
    ET.SubElement(world_ctrl, "step").text = "true"
    ET.SubElement(world_ctrl, "start_paused").text = "true"

    # Embed original model into world
    world.append(_deep_copy(model))

    # Add Tugbot include
    include = ET.SubElement(world, "include")
    ET.SubElement(include, "uri").text = "Tugbot"
    ET.SubElement(include, "pose").text = "1 0 0.3 0 0 0"

    # Save new file and copy Tugbot model folder
    new_content = pretty_print_clean(sdf_out)
    new_path = _make_new_path(src_path)
    with open(new_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    _copy_tugbot_folder(src_path.parent, tugbot_source_dir)

    return str(new_path)


def spawn_sdf_with_agv(path: str, ros_setup: str = "/opt/ros/jazzy/setup.bash") -> str:
    """Launch a generated SDF world with Tugbot inside Gazebo.

    Workflow:
      1. Transform the input SDF to include Tugbot (via create_sdf_with_agv).
      2. Source ROS environment setup (e.g. Jazzy).
      3. Prefer modern Gazebo (`gz sim`), fallback to classic `gazebo`.
      4. Launch the simulation as a subprocess.

    Args:
        path: Path to the original model/world SDF file.
        ros_setup: Path to the ROS environment setup script.

    Returns:
        str: Confirmation message with the world file path.

    Raises:
        FileNotFoundError: If required files are missing.
        RuntimeError: If no Gazebo executable is available.
    """
    world_path = create_sdf_with_agv(path)

    world = Path(world_path).expanduser().resolve()
    if not world.exists():
        raise FileNotFoundError(f"World file not found: {world}")

    ros_setup_path = Path(ros_setup)
    if not ros_setup_path.exists():
        raise FileNotFoundError(f"ROS setup file not found: {ros_setup_path}")

    def _bash(cmd: str) -> subprocess.CompletedProcess:
        """Run a bash command after sourcing the ROS environment."""
        full = f"source {shlex.quote(str(ros_setup_path))} >/dev/null 2>&1 && {cmd}"
        return subprocess.run(
            ["bash", "-lc", full],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    gz_present = _bash("command -v gz >/dev/null 2>&1; echo $?").stdout.strip() == "0"
    gz_sim_ok = False
    if gz_present:
        chk = _bash("gz sim --help >/dev/null 2>&1; echo $?")
        gz_sim_ok = chk.stdout.strip() == "0"

    gazebo_present = False
    if not gz_sim_ok:
        gazebo_present = (
            _bash("command -v gazebo >/dev/null 2>&1; echo $?").stdout.strip() == "0"
        )

    if not gz_sim_ok and not gazebo_present:
        raise RuntimeError(
            "Gazebo not found.\n"
            "Checked for both `gz sim` and `gazebo` after sourcing ROS.\n"
            "Please install Gazebo (Garden+ uses `gz sim`, classic uses `gazebo`)."
        )

    if gz_sim_ok:
        launch_cmd = f"source {shlex.quote(str(ros_setup_path))} && gz sim {shlex.quote(str(world))}"
    else:
        launch_cmd = f"source {shlex.quote(str(ros_setup_path))} && gazebo {shlex.quote(str(world))}"

    subprocess.Popen(
        ["bash", "-lc", launch_cmd],
        cwd=str(world.parent),
        env={**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")},
        stdin=None,
        stdout=None,
        stderr=None,
        preexec_fn=os.setsid,
    )
    return f"Spawned generated World file with AGV {world_path}"


def main():
    spawn_sdf_with_agv(
        "home/RUS_CIP/st185769/VSCode/MT3861_LLM_Communication/data/Case_5/warehouse_worlds/sample3.sdf"
    )


if __name__ == "__main__":
    main()
