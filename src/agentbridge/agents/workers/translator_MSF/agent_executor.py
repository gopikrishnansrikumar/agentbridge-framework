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
from agent import TranslatorMSFAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TranslatorMSFAgentExecutor(AgentExecutor):
    """
    Execution layer for the Translator MSF Agent.
    
    Responsible for:
      - Validating incoming requests
      - Starting new tasks if necessary
      - Streaming intermediate and final responses from the agent
      - Updating task state and artifacts in the event queue
    """

    def __init__(self):
        # Initialize with an instance of the TranslatorMSFAgent
        self.agent = TranslatorMSFAgent()

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """
        Handle execution of a single request.
        Streams results from the TranslatorMSFAgent into the event queue.
        """
        error = self._validate_request(context)
        if error:
            # If request is invalid, raise immediately
            raise ServerError(error=InvalidParamsError())

        query = context.get_user_input()
        task = context.current_task

        # Create a new task if this is the first request in the context
        if not task:
            task = new_task(context.message)
            event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue, task.id, task.contextId)

        try:
            # Stream agent outputs step by step
            async for item in self.agent.stream(query, task.contextId):
                is_task_complete = item["is_task_complete"]
                require_user_input = item["require_user_input"]

                if not is_task_complete and not require_user_input:
                    # Agent is still working → emit intermediate status
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
                    # Agent requires more input from the user
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
                    # Agent finished successfully → attach artifact and complete task
                    updater.add_artifact(
                        [Part(root=TextPart(text=content))],
                        name="msf_translation",
                    )
                    updater.complete()
                    break

        except Exception as e:
            logger.error(f"An error occurred while streaming the response: {e}")
            raise ServerError(error=InternalError()) from e

    def _validate_request(self, context: RequestContext) -> bool:
        """
        Perform request validation (stub).
        Returns False for now, meaning all requests are considered valid.
        """
        return False

    async def cancel(
        self, request: RequestContext, event_queue: EventQueue
    ) -> Task | None:
        """
        Cancellation is not supported for this executor.
        Always raises UnsupportedOperationError.
        """
        raise ServerError(error=UnsupportedOperationError())
