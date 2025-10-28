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
from agent import TranslatorURDFAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TranslatorURDFAgentExecutor(AgentExecutor):
    """
    Execution layer for the Translator URDF Agent.

    Responsibilities:
      - Validate incoming requests
      - Initialize new tasks when needed
      - Stream intermediate and final results from the agent
      - Update the event queue with progress and final artifacts
    """

    def __init__(self):
        # Create an instance of the Translator URDF Agent
        self.agent = TranslatorURDFAgent()

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """
        Execute a single request by streaming responses from the Translator URDF Agent.
        Updates task state (working, input required, completed) as results are produced.
        """
        error = self._validate_request(context)
        if error:
            raise ServerError(error=InvalidParamsError())

        query = context.get_user_input()
        task = context.current_task

        # If no task exists, create a new one and enqueue it
        if not task:
            task = new_task(context.message)
            event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue, task.id, task.contextId)

        try:
            # Stream responses incrementally from the agent
            async for item in self.agent.stream(query, task.contextId):
                is_task_complete = item["is_task_complete"]
                require_user_input = item["require_user_input"]

                if not is_task_complete and not require_user_input:
                    # Agent is still processing → update with intermediate status
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
                    # Agent is requesting additional input from the user
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
                    # Agent completed successfully → save result as artifact
                    updater.add_artifact(
                        [Part(root=TextPart(text=content))],
                        name="urdf_translation",
                    )
                    updater.complete()
                    break

        except Exception as e:
            logger.error(f"An error occurred while streaming the response: {e}")
            raise ServerError(error=InternalError()) from e

    def _validate_request(self, context: RequestContext) -> bool:
        """
        Validate the request (stub implementation).
        Currently always returns False → all requests are accepted.
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
