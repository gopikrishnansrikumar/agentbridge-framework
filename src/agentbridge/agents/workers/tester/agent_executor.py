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
from a2a.utils import (
    new_agent_text_message,
    new_task,
)
from a2a.utils.errors import ServerError
from agent import ValidatorAgent
from typing_extensions import override

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ValidatorAgentExecutor(AgentExecutor):
    """SDF Validator AgentExecutor."""

    def __init__(self):
        self.agent = ValidatorAgent()

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
                        name="testing_validation",
                    )
                    updater.complete()
                    break

        except Exception as e:
            logger.error(f"An error occurred while streaming the response: {e}")
            raise ServerError(error=InternalError()) from e

    def _validate_request(self, context: RequestContext) -> bool:
        return False

    async def cancel(
        self, request: RequestContext, event_queue: EventQueue
    ) -> Task | None:
        raise ServerError(error=UnsupportedOperationError())
