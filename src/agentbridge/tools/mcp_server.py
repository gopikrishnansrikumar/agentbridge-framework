import os

import utils.agent_tools as agent_tools
import utils.machine_feedback as machine_feedback
import utils.spawner_scripts as spawner_tools
import utils.unit_tests_MJCF as unit_tests_MJCF
import utils.unit_tests_SDF as unit_tests_SDF
import utils.unit_tests_URDF as unit_tests_URDF
from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langsmith import traceable
from mcp.server.fastmcp import FastMCP

# Initialize MCP server for AgentBridge
mcp = FastMCP("AgentBridge MCP Server")

# Load vector embeddings once at startup (shared by all retrieval tools)
embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

# Chroma vector databases for retrieval-augmented generation (RAG)
vectorstore_sdf = Chroma(
    persist_directory="data/RAG_SDF/chroma_gazebo_db",
    embedding_function=embeddings,
)
vectorstore_urdf = Chroma(
    persist_directory="data/RAG_URDF/chroma_gazebo_db",
    embedding_function=embeddings,
)
vectorstore_msf = Chroma(
    persist_directory="data/RAG_MSF/chroma_gazebo_db",
    embedding_function=embeddings,
)


@mcp.tool()
async def list_tools_tool() -> str:
    """List all tools available in the MCP server.

    Returns:
        str: Formatted list of tool names and descriptions.
    """
    return await agent_tools.list_tools()


@mcp.tool()
async def read_mjcf_file(path: str) -> str:
    """Read an MJCF (MuJoCo XML) file from the given path and return its
    contents as a string.

    Args:
        path (str): Path to the MJCF XML file.

    Returns:
        str: The contents of the MJCF file.
    """
    return await agent_tools.read_mjcf_file(path)


@mcp.tool()
async def read_sdf_file(path: str) -> str:
    """Read an SDF (Simulation Description Format) file from the given path and
    return its contents as a string.

    Args:
        path (str): Path to the SDF file.

    Returns:
        str: The contents of the SDF file.
    """
    return await agent_tools.read_sdf_file(path)


@mcp.tool()
async def read_msf_file(path: str) -> str:
    """Read an MSF (Mock Simulation Format) file from the given path and return
    its contents as a string.

    Args:
        path (str): Path to the MSF file.

    Returns:
        str: The contents of the SMSFDF file.
    """
    return await agent_tools.read_msf_file(path)


@mcp.tool()
async def read_urdf_file(path: str) -> str:
    """Read a URDF (Unified Robot Description Format) file from the given path
    and return its contents as a string.

    Args:
        path (str): Path to the URDF file.

    Returns:
        str: The contents of the URDF file.
    """
    return await agent_tools.read_urdf_file(path)


@mcp.tool()
def update_sdf_file(new_content: str, path: str) -> str:
    """Overwrite an existing SDF (Simulation Description Format) file with new
    content.

    Args:
        new_content (str): The new content to write into the file.
        path (str): Path to the SDF file to update.

    Returns:
        str: A status message indicating success or failure.
    """
    return agent_tools.update_sdf_file(new_content, path)


@mcp.tool()
def update_urdf_file(new_content: str, path: str) -> str:
    """Overwrite an existing URDF (Unified Robot Description Format) file with
    new content.

    Args:
        new_content (str): The new content to write into the file.
        path (str): Path to the URDF file to update.

    Returns:
        str: A status message indicating success or failure.
    """
    return agent_tools.update_urdf_file(new_content, path)


@mcp.tool()
async def save_description_NL(
    description: str, path: str = "data/description/description.txt"
) -> str:
    """Save the provided natural language description to a text(.txt)file. The
    natural language description can be a detailed explanation of a file and is
    saved in a human-readable txt format.

    Args:
        description (str): The natural language description to save.
        path (str, optional): Path where to save the text file. Defaults to "data/description/description.txt".

    Returns:
        str: Confirmation message with the saved path.
    """
    return agent_tools.save_natural_language_description(description, path)


@mcp.tool()
async def save_description_JSON(
    json_data: dict, path: str = "data/description/description.json"
) -> str:
    """Save the provided structured JSON description to a JSON(.json) file. The
    JSON description can include metadata, file paths, and other structured
    information about the file is saved in a human-readable json format.

    Args:
        json_data (dict): The JSON data to save.
        path (str, optional): Path where to save the JSON file. Defaults to "data/description/description.json".

    Returns:
        str: Confirmation message with the saved path.
    """
    return agent_tools.save_json_description(json_data, path)


@mcp.tool()
async def read_description_file_NL(path: str) -> str:
    """Read a natural language description from a text file.

    Args:
        path (str): Path to the text file containing the description.

    Returns:
        str: Contents of the file as a string.
    """
    return await agent_tools.read_natural_language_description(path)


@mcp.tool()
async def read_description_file_JSON(path: str) -> dict:
    """Read a structured JSON description from a JSON file.

    Args:
        path (str): Path to the JSON file.

    Returns:
        dict: Parsed JSON data as a Python dictionary.
    """
    return await agent_tools.read_json_description(path)


@mcp.tool()
async def save_sdf_file(content: str, mjcf_path: str, path: str) -> str:
    """Save the generated SDF (Simulation Description Format) content to a file
    with .sdf extension to the provided path.

    Args:
        content (str): The SDF file contents.
        mjcf_path (str): Path to the original MJCF file.
        path (str, optional): Path where to save the SDF file. Defaults to "data/generated.sdf".

    Returns:
        str: Confirmation message with the saved path.
    """
    return agent_tools.save_sdf(content, mjcf_path, path)


@mcp.tool()
async def save_urdf_file(content: str, path: str = "static/generated.urdf") -> str:
    """Save the generated URDF (Unified Robot Description Format) content to a
    file with .urdf extension to the provided path.

    Args:
        content (str): The URDF file contents.
        path (str, optional): Path where to save the URDF file. Defaults to "static/generated.urdf".

    Returns:
        str: Confirmation message with the saved path.
    """
    return agent_tools.save_urdf(content, path)


@mcp.tool()
async def validate_sdf_file(path: str = "data/sdf/output.sdf") -> str:
    """Validate an SDF (Simulation Description Format) file and return a
    detailed report of the validation from unit tests.

    Args:
        path (str): Path to the SDF file.

    Returns:
        str: Detailed test report from the SDF validator.
    """
    if not os.path.exists(path):
        return f"❌ File not found: {path}"
    # This can be made async if needed, but unit tests are fast and synchronous.
    return unit_tests_SDF.validate_sdf_with_report(path)


@mcp.tool()
async def validate_urdf_file(path: str = "data/urdf/output.urdf") -> str:
    """Validate a URDF (Unified Robot Description Format) file and return a
    detailed report of the validation from unit tests.

    Args:
        path (str): Path to the URDF file.

    Returns:
        str: Detailed test report from the URDF validator.
    """
    if not os.path.exists(path):
        return f"❌ File not found: {path}"
    # This can be made async if needed, but unit tests are fast and synchronous.
    return unit_tests_URDF.validate_urdf_with_report(path)


@mcp.tool()
async def validate_mjcf_file(path: str = "data/mjcf/input.xml") -> str:
    """Validate a MJCF (MuJoCo XML) file and return a detailed report of the
    validation from unit tests.

    Args:
        path (str): Path to the MJCF file.

    Returns:
        str: Detailed test report from the MJCF validator.
    """
    if not os.path.exists(path):
        return f"❌ File not found: {path}"

    return unit_tests_MJCF.validate_mjcf_with_report(path)


@mcp.tool()
async def retrieve_few_shot_examples_sdf(path: str, k: int = 3) -> str:
    """Retrieve the top-k relevant MJCF/SDF examples from the SDF RAG database
    for few-shot prompting and return them as a single formatted string.

    Args:
        path (str): Path to the MJCF XML file.
        k (int): Number of examples to retrieve.

    Returns:
        str: A formatted string concatenating each example’s metadata and content preview.
    """
    query = await agent_tools.read_mjcf_file(path)
    results = vectorstore_sdf.similarity_search(query, k=k)
    examples_rag = ""
    for i, doc in enumerate(results, start=1):
        examples_rag += f"\n--- RAG Example {i} ---\n"
        examples_rag += f"Metadata: {doc.metadata}\n"
        examples_rag += f"Content preview: {doc.page_content}\n"
    return examples_rag


@mcp.tool()
async def retrieve_few_shot_examples_urdf(path: str, k: int = 3) -> str:
    """Retrieve the top-k relevant MJCF/URDF examples from the URDF RAG
    database for few-shot prompting and return them as a single formatted
    string.

    Args:
        path (str): Path to the MJCF XML file.
        k (int): Number of examples to retrieve.

    Returns:
        str: A formatted string concatenating each example’s metadata and content preview.
    """
    query = await agent_tools.read_mjcf_file(path)
    results = vectorstore_urdf.similarity_search(query, k=k)
    examples_rag = ""
    for i, doc in enumerate(results, start=1):
        examples_rag += f"\n--- RAG Example {i} ---\n"
        examples_rag += f"Metadata: {doc.metadata}\n"
        examples_rag += f"Content preview: {doc.page_content}\n"
    return examples_rag


@mcp.tool()
async def retrieve_few_shot_examples_msf(path: str, k: int = 3) -> str:
    """Retrieve the top-k relevant MSF/SDF examples from the MSF RAG database
    for few-shot prompting and return them as a single formatted string.

    Args:
        path (str): Path to the MJCF XML file.
        k (int): Number of examples to retrieve.

    Returns:
        str: A formatted string concatenating each example’s metadata and content preview.
    """
    query = await agent_tools.read_msf_file(path)
    results = vectorstore_msf.similarity_search(query, k=k)
    examples_rag = ""
    for i, doc in enumerate(results, start=1):
        examples_rag += f"\n--- RAG Example {i} ---\n"
        examples_rag += f"Metadata: {doc.metadata}\n"
        examples_rag += f"Content preview: {doc.page_content}\n"
    return examples_rag


@mcp.tool()
async def debug_robot_file_with_gazebo(path: str = "data/sdf/model.sdf") -> str:
    """Debug a robot description file (.sdf or .urdf) using Gazebo tools and
    runtime checks.

    This includes:
    - Gazebo CLI check
    - URDF to SDF conversion (if needed)
    - SDF syntax validation
    - Gazebo headless simulation
    - URI/mesh resolution

    Args:
        path (str): Path to the robot description file

    Returns:
        str: Markdown-formatted debug report
    """
    if not os.path.exists(path):
        return f"❌ File not found: {path}"

    return machine_feedback.generate_debug_report(path)


@mcp.tool()
async def spawn_agv_gazebo(path: str = "data/sdf/model.sdf") -> str:
    """Build a Gazebo-ready world from a model SDF with AGV included and launch
    it.

    Args:
        path: Path to a model-only SDF (or an SDF already containing a `<world>`)

    Returns:
        str: Path to the udpated sdf worlf file

    Raises:
        FileNotFoundError: If the input file or ROS setup file is missing.
        RuntimeError: If neither `gz sim` nor `gazebo` is available.
    """
    if not os.path.exists(path):
        return f"❌ File not found: {path}"  # type:ignore

    return spawner_tools.spawn_sdf_with_agv(path)

# Run MCP server with SSE transport (server-sent events)
mcp.run(transport="sse")
