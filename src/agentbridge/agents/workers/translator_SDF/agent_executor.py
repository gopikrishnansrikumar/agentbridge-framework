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
from agent import TranslatorSDFAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TranslatorSDFAgentExecutor(AgentExecutor):
    """
    Execution layer for the Translator SDF Agent.

    Handles:
      - Validating incoming requests
      - Initializing or resuming tasks
      - Streaming intermediate and final results from the agent
      - Updating the event queue with task state and artifacts
    """

    def __init__(self):
        # Create an instance of the TranslatorSDFAgent
        self.agent = TranslatorSDFAgent()

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """
        Execute a single request by streaming results from the Translator SDF Agent.
        Updates task state (working, input required, completed) as responses arrive.
        """
        error = self._validate_request(context)
        if error:
            raise ServerError(error=InvalidParamsError())

        query = context.get_user_input()
        task = context.current_task

        # If no task is active, create a new one and enqueue it
        if not task:
            task = new_task(context.message)
            event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue, task.id, task.contextId)

        try:
            # Stream incremental outputs from the agent
            async for item in self.agent.stream(query, task.contextId):
                is_task_complete = item["is_task_complete"]
                require_user_input = item["require_user_input"]

                if not is_task_complete and not require_user_input:
                    # Agent is still working → emit ongoing status
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
                    # Agent is requesting more input from the user
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
                    # Agent completed successfully → attach translation result as artifact
                    updater.add_artifact(
                        [Part(root=TextPart(text=content))],
                        name="sdf_translation",
                    )
                    updater.complete()
                    break

        except Exception as e:
            logger.error(f"An error occurred while streaming the response: {e}")
            raise ServerError(error=InternalError()) from e

    def _validate_request(self, context: RequestContext) -> bool:
        """
        Validate incoming request (stub implementation).
        Returns False, meaning all requests are currently accepted.
        """
        return False

    async def cancel(
        self, request: RequestContext, event_queue: EventQueue
    ) -> Task | None:
        """
        Cancel is not supported for this executor.
        Always raises UnsupportedOperationError.
        """
        raise ServerError(error=UnsupportedOperationError())
