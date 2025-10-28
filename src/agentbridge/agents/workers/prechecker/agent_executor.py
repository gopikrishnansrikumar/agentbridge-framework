"""
Prechecker Agent Executor.

This module defines the PrecheckerAgentExecutor, which bridges the PrecheckerAgent
and the A2A (Agent-to-Agent) execution framework. It handles:
  - Validating incoming requests
  - Managing task lifecycle events
  - Streaming responses back to the event queue
  - Converting agent outputs into artifacts and task updates

The PrecheckerAgent itself performs validation of MJCF (MuJoCo XML) files.
This executor ensures that the Prechecker runs within the orchestrated
multi-agent system, producing both real-time updates and final artifacts.
"""

import logging

from a2a.server.agent_execution import AgentExecutor, RequestContext  # type: ignore
from a2a.server.events import EventQueue  # type: ignore
from a2a.server.tasks import TaskUpdater  # type: ignore
from a2a.types import (
    InternalError,
    InvalidParamsError,
    Part,  # type: ignore
    Task,
    TaskState,
    TextPart,
    UnsupportedOperationError,
)
from a2a.utils import new_agent_text_message, new_task  # type: ignore
from a2a.utils.errors import ServerError  # type: ignore
from agent import PrecheckerAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PrecheckerAgentExecutor(AgentExecutor):
    """
    AgentExecutor wrapper for the MJCF Prechecker Agent.

    Responsibilities:
        - Instantiate and run the PrecheckerAgent
        - Create or reuse tasks for incoming requests
        - Stream intermediate outputs (working state)
        - Capture final outputs as artifacts
        - Mark tasks as completed or requiring user input

    The Prechecker validates MJCF XML structure before downstream pipeline stages.
    """

    def __init__(self):
        """Initialize executor with a PrecheckerAgent instance."""
        self.agent = PrecheckerAgent()

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """
        Execute the PrecheckerAgent against an incoming request.

        Args:
            context: RequestContext containing the user query, current task, etc.
            event_queue: EventQueue to which updates and events will be enqueued.

        Raises:
            ServerError: if request validation fails or internal errors occur.
        """
        error = self._validate_request(context)
        if error:
            raise ServerError(error=InvalidParamsError())

        # Ensure task exists (reuse if continuing, else create new)
        query = context.get_user_input()
        task = context.current_task
        if not task:
            task = new_task(context.message)
            event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue, task.id, task.contextId)

        try:
            # Stream output from the PrecheckerAgent
            async for item in self.agent.stream(query, task.contextId):
                is_task_complete = item["is_task_complete"]
                require_user_input = item["require_user_input"]

                if not is_task_complete and not require_user_input:
                    # Case: agent is still working → update task progress
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

                elif require_user_input:
                    # Case: agent requests user input → pause and mark final
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

                else:
                    # Case: task is complete → attach artifact and finalize
                    updater.add_artifact(
                        [Part(root=TextPart(text=content))],
                        name="mjcf_precheck",
                    )
                    updater.complete()
                    break

        except Exception as e:
            logger.error(f"An error occurred while streaming the response: {e}")
            raise ServerError(error=InternalError()) from e

    def _validate_request(self, context: RequestContext) -> bool:
        """
        Validate the incoming request.

        Currently, always returns False (no validation errors).
        Could be extended to check input schema or supported modes.

        Args:
            context: The request context to validate.

        Returns:
            bool: True if validation fails, False otherwise.
        """
        return False

    async def cancel(
        self, request: RequestContext, event_queue: EventQueue
    ) -> Task | None:
        """
        Cancel the execution of a Prechecker task.

        Currently unsupported for this agent.

        Raises:
            ServerError: always, with UnsupportedOperationError.
        """
        raise ServerError(error=UnsupportedOperationError())
