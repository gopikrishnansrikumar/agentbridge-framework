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
from agent import DebuggerAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DebuggerAgentExecutor(AgentExecutor):
    """
    AgentExecutor implementation for the DebuggerAgent.

    Responsibilities:
      - Accept incoming requests from the A2A server layer.
      - Stream execution results from the DebuggerAgent back to clients.
      - Update task state (working, input required, completed, etc.) as results arrive.
      - Handle errors gracefully and translate them into standardized server errors.
    """

    def __init__(self):
        # Instantiate the underlying DebuggerAgent (defined in agent.py).
        self.agent = DebuggerAgent()

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """
        Execute a debugging request.

        Workflow:
          1. Validate input request.
          2. Create a new task if one does not exist yet.
          3. Stream results from DebuggerAgent (async generator).
          4. Update the task state dynamically:
             - working (intermediate results)
             - input_required (agent needs user feedback)
             - complete (final artifact produced)
          5. Handle exceptions and propagate as standardized errors.

        Args:
            context: Request context including message and task metadata.
            event_queue: EventQueue to publish task updates.
        """
        error = self._validate_request(context)
        if error:
            raise ServerError(error=InvalidParamsError())

        query = context.get_user_input()
        task = context.current_task

        # If no task is provided, create and enqueue a new one
        if not task:
            task = new_task(context.message)
            event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue, task.id, task.contextId)

        try:
            async for item in self.agent.stream(query, task.contextId):
                is_task_complete = item["is_task_complete"]
                require_user_input = item["require_user_input"]

                if not is_task_complete and not require_user_input:
                    # Intermediate progress update
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
                    # Pause execution: waiting for human input
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
                    # Final result: save as artifact and complete task
                    updater.add_artifact(
                        [Part(root=TextPart(text=content))],
                        name="debugger",
                    )
                    updater.complete()
                    break

        except Exception as e:
            logger.error(f"An error occurred while streaming the response: {e}")
            raise ServerError(error=InternalError()) from e

    def _validate_request(self, context: RequestContext) -> bool:
        """
        Validate the incoming request.

        For now, always returns False (no validation errors).
        Could be extended later to check for malformed input.
        """
        return False

    async def cancel(
        self, request: RequestContext, event_queue: EventQueue
    ) -> Task | None:
        """
        Cancel execution of an ongoing task.

        Currently unsupported for the DebuggerAgent, so always raises error.
        """
        raise ServerError(error=UnsupportedOperationError())
