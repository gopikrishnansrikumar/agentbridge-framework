"""
Spawner Agent Executor.

This module implements the `SpawnerAgentExecutor`, which integrates the SpawnerAgent
with the A2A (Agent-to-Agent) server runtime. The executor acts as a bridge between
incoming user requests (via RequestContext) and the agent's streaming responses.

Responsibilities:
  - Validate incoming requests before execution.
  - Translate user queries into tasks managed by the A2A event system.
  - Stream results from the SpawnerAgent back to the client in real-time.
  - Update task state (working, input required, or completed).
  - Save final artifacts when a task completes successfully.

This executor ensures that the SpawnerAgent follows the correct lifecycle in the
multi-agent robotics pipeline.
"""

import logging

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    InternalError,
    InvalidParamsError,
    Part,
    Task,
    TaskState,
    TextPart,
    UnsupportedOperationError,
)
from a2a.utils import new_agent_text_message, new_task
from a2a.utils.errors import ServerError
from agent import SpawnerAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SpawnerAgentExecutor(AgentExecutor):
    """
    Executor for the Spawner Agent.

    The executor manages the lifecycle of a spawning task:
      - Receives input requests from the orchestrator.
      - Invokes the SpawnerAgent to process the task.
      - Streams intermediate progress updates.
      - Returns artifacts representing updated world files (SDF/URDF).
    """

    def __init__(self):
        # Initialize a single agent instance for handling requests
        self.agent = SpawnerAgent()

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """
        Main execution entrypoint for handling a user task.

        Args:
            context: RequestContext containing the user query and current task info.
            event_queue: EventQueue for publishing updates back to the orchestrator.

        Raises:
            ServerError: If validation fails or if an internal error occurs.
        """
        # Step 1: Validate request before proceeding
        error = self._validate_request(context)
        if error:
            raise ServerError(error=InvalidParamsError())

        # Step 2: Extract user query and initialize a task if none exists
        query = context.get_user_input()
        task = context.current_task
        if not task:
            task = new_task(context.message)
            event_queue.enqueue_event(task)

        # Step 3: Create a task updater for managing task state and artifacts
        updater = TaskUpdater(event_queue, task.id, task.contextId)

        try:
            # Step 4: Stream results from the SpawnerAgent
            async for item in self.agent.stream(query, task.contextId):
                is_task_complete = item["is_task_complete"]
                require_user_input = item["require_user_input"]

                # Case A: Task is still ongoing, no user input required
                if not is_task_complete and not require_user_input:
                    # Intermediate working update
                    content = item["content"]
                    if isinstance(content, list):
                        # If the agent returns multiple pieces, join them into one string
                        content = " ".join(map(str, content))

                    updater.update_status(
                        TaskState.working,
                        new_agent_text_message(
                            content,
                            task.contextId,
                            task.id,
                        ),
                    )

                # Case B: Task execution paused, requires additional user input
                elif require_user_input:
                    # Pause execution, requesting additional input from user
                    content = item["content"]
                    if isinstance(content, list):
                        # If the agent returns multiple pieces, join them into one string
                        content = " ".join(map(str, content))

                    updater.update_status(
                        TaskState.input_required,
                        new_agent_text_message(
                            content,
                            task.contextId,
                            task.id,
                        ),
                        final=True,
                    )
                    break

                # Case C: Task finished successfully → save artifact + mark complete
                else:
                    updater.add_artifact(
                        [Part(root=TextPart(text=content))],
                        name="gazebo_spawn",  # artifact name for spawned world results
                    )
                    updater.complete()
                    break

        except Exception as e:
            logger.error(f"An error occurred while streaming the response: {e}")
            # Wrap internal errors for consistency
            raise ServerError(error=InternalError()) from e

    def _validate_request(self, context: RequestContext) -> bool:
        """
        Perform lightweight request validation.

        Returns:
            bool: False if request is valid, True if invalid.
        """
        return False  # currently all requests are treated as valid

    async def cancel(
        self, request: RequestContext, event_queue: EventQueue
    ) -> Task | None:
        """
        Cancel an in-progress task.

        This executor does not support cancellation; all requests must run
        to completion.

        Raises:
            ServerError: Always, with UnsupportedOperationError.
        """
        raise ServerError(error=UnsupportedOperationError())
