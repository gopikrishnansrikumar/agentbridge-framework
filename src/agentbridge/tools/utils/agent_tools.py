import asyncio
import json
import os
from typing import List

from langchain_mcp_adapters.client import MultiServerMCPClient


async def read_mjcf_file(
    path: str,
    *,
    max_depth: int = 2,
    include_hidden: bool = False,
    follow_symlinks: bool = False,
) -> str:
    """Read an MJCF file and also collect relative paths of related assets
    (e.g. meshes and textures). This helps preserve links between model
    descriptions and their resources.

    Args:
        path: Path to the MJCF file.
        max_depth: Directory depth to search for related files.
        include_hidden: Whether to include hidden files/folders.
        follow_symlinks: Whether to traverse symbolic links.

    Returns:
        str: File content followed by a list of related asset paths.
    """
    path = (path or "").strip().strip("'").strip('"')
    path = os.path.abspath(os.path.expanduser(path))
    print(f"[read_mjcf_file] Opening path: '{path}'")

    if not os.path.exists(path):
        return f"File not found: {path}"
    if not os.path.isfile(path):
        return f"Path is not a file: {path}"

    root_dir = os.path.dirname(path)
    exts = {".obj", ".mtl", ".jpg", ".jpeg", ".png"}

    def _is_hidden(name: str) -> bool:
        return name.startswith(".")

    def _collect_files(d: str, depth: int) -> List[str]:
        """Recursively search for related asset files up to a given depth."""
        if depth < 0:
            return []
        results: List[str] = []
        try:
            with os.scandir(d) as it:
                entries = list(it)
        except (PermissionError, FileNotFoundError):
            return []

        if not include_hidden:
            entries = [e for e in entries if not _is_hidden(e.name)]

        for e in entries:
            entry_path = os.path.join(d, e.name)
            if e.is_dir(follow_symlinks=follow_symlinks) and depth > 0:
                results.extend(_collect_files(entry_path, depth - 1))
            else:
                if os.path.splitext(e.name)[1].lower() in exts:
                    rel_path = os.path.relpath(entry_path, root_dir)
                    results.append(rel_path)
        return results

    def _read_file_sync() -> str:
        """Helper to safely read the MJCF file as text."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except UnicodeDecodeError:
            with open(path, "r", errors="replace") as f:
                return f.read()
        except Exception as e:
            return f"Exception occurred while reading file: {e}"

    # Run potentially blocking file operations in threads
    content = await asyncio.to_thread(_read_file_sync)
    related_files = await asyncio.to_thread(_collect_files, root_dir, max_depth)

    related_section = (
        "Related important files:\n" + "\n".join(related_files)
        if related_files
        else "Related important files: (none found)"
    )

    return f"MJCF file content:\n{content}\n\n{related_section}"


async def read_sdf_file(path: str) -> str:
    """Read an SDF file and return its raw content."""
    path = path.strip().strip("'").strip('"')
    path = os.path.abspath(os.path.expanduser(path))
    print(f"[read_sdf_file] Opening path: '{path}'")
    if not os.path.exists(path):
        return f"File not found: {path}"
    try:
        with open(path, "r") as f:
            return f.read()
    except Exception as e:
        return f"Exception occurred while reading file: {e}"


async def read_urdf_file(path: str) -> str:
    """Read a URDF file and return its raw content."""
    path = path.strip().strip("'").strip('"')
    path = os.path.abspath(os.path.expanduser(path))
    print(f"[read_urdf_file] Opening path: '{path}'")
    if not os.path.exists(path):
        return f"File not found: {path}"
    try:
        with open(path, "r") as f:
            return f.read()
    except Exception as e:
        return f"Exception occurred while reading file: {e}"


async def read_msf_file(path: str) -> str:
    """Read an MSF (Mock Simulation Format) file and return its content."""
    path = path.strip().strip("'").strip('"')
    path = os.path.abspath(os.path.expanduser(path))
    print(f"[read_msf_file] Opening path: '{path}'")

    if not os.path.exists(path):
        return f"File not found: {path}"

    try:
        with open(path, "r") as f:
            return f.read()
    except Exception as e:
        return f"Exception occurred while reading file: {e}"


def update_sdf_file(new_content: str, path: str) -> str:
    """Overwrite an existing SDF file with new content."""
    path = path.strip().strip("'").strip('"')
    path = os.path.abspath(os.path.expanduser(path))
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(new_content)
        print(f"SDF file updated at {path}")
        return f"SDF file updated at {path}"
    except Exception as e:
        msg = f"Exception occurred while updating SDF file: {e}"
        print(msg)
        return msg


def update_urdf_file(new_content: str, path: str) -> str:
    """Overwrite an existing URDF file with new content."""
    path = path.strip().strip("'").strip('"')
    path = os.path.abspath(os.path.expanduser(path))
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(new_content)
        print(f"URDF file updated at {path}")
        return f"URDF file updated at {path}"
    except Exception as e:
        msg = f"Exception occurred while updating URDF file: {e}"
        print(msg)
        return msg


def save_natural_language_description(
    description: str, path: str = "data/description/description.txt"
) -> str:
    """Save a free-text natural language description into a .txt file."""
    path = path.strip().strip("'").strip('"')
    path = os.path.abspath(os.path.expanduser(path))
    path = "data/description/description.txt"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(description)
        print(f"Natural language description saved to {path}")
        return f"Natural language description saved to {path}"
    except Exception as e:
        return f"Exception occurred while saving file: {e}"


def save_json_description(
    json_data: dict, path: str = "data/description/description.json"
) -> str:
    """Save structured description metadata into a .json file."""
    path = path.strip().strip("'").strip('"')
    path = os.path.abspath(os.path.expanduser(path))
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(json_data, f, indent=2)
        return f"JSON description saved to {path}"
    except Exception as e:
        return f"Exception occurred while saving JSON file: {e}"


def save_sdf(text: str, mjcf_path: str, path: str) -> str:
    """Save generated SDF content near its source MJCF file.
    Ensures correct file extension and directory placement.
    """
    try:
        mjcf_dir = os.path.dirname(os.path.abspath(os.path.expanduser(mjcf_path)))
        mjcf_stem = os.path.splitext(os.path.basename(mjcf_path))[0]

        raw_hint = (path or "").strip().strip("'").strip('"')
        filename_hint = os.path.basename(raw_hint)

        if not filename_hint:
            filename = f"{mjcf_stem}.sdf"
        else:
            base, ext = os.path.splitext(filename_hint)
            filename = f"{base}.sdf" if ext.lower() != ".sdf" else filename_hint

        full_path = os.path.join(mjcf_dir, filename)

        os.makedirs(mjcf_dir, exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(text)

        return f"SDF saved to {full_path}"
    except Exception as e:
        return f"Exception occurred while saving SDF file: {e}"


def save_urdf(text: str, path: str = "static/generated.urdf") -> str:
    """Save generated URDF content to disk."""
    path = path.strip().strip("'").strip('"')
    path = os.path.abspath(os.path.expanduser(path))
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)
        return f"URDF saved to {path}"
    except Exception as e:
        return f"Exception occurred while saving URDF file: {e}"


async def read_natural_language_description(
    path: str = "data/description/description.txt",
) -> str:
    """Read a natural language description from a text file."""
    path = path.strip().strip("'").strip('"')
    path = "data/description/description.txt"
    print(f"[read_natural_language_description] Opening path: '{path}'")
    if not os.path.exists(path):
        return f"[Error] Natural language description file not found at {path}."
    try:
        with open(path, "r") as f:
            return f.read()
    except Exception as e:
        return f"Exception occurred while reading description: {e}"


async def read_json_description(
    path: str = "data/description/description.json",
) -> dict:
    """Read a structured description from a JSON file."""
    path = path.strip().strip("'").strip('"')
    print(f"[read_json_description] Opening path: '{path}'")
    if not os.path.exists(path):
        return f"[Error] JSON description file not found at {path}."  # type: ignore
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception as e:
        return f"Exception occurred while reading JSON: {e}"  # type: ignore
