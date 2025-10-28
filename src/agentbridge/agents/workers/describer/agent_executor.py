import logging

from a2a.server.agent_execution import AgentExecutor  # type: ignore
from a2a.server.agent_execution import RequestContext
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
from agent import DescriberAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DescriberAgentExecutor(AgentExecutor):
    """
    Executor class for the DescriberAgent.

    Responsibilities:
      - Accepts execution requests from the A2A server layer.
      - Streams outputs from the DescriberAgent and translates them into task updates.
      - Publishes intermediate messages, requests for input, or final artifacts.
      - Ensures task lifecycle transitions (working → input_required → completed).
    """

    def __init__(self):
        # Instantiate the DescriberAgent defined in agent.py
        self.agent = DescriberAgent()

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """
        Main execution entrypoint for a describer request.

        Steps:
          1. Validate input request (currently always passes).
          2. Create or reuse a task associated with this request.
          3. Call DescriberAgent.stream() to process the input query.
          4. Update the task state dynamically as results arrive:
             - TaskState.working for intermediate progress.
             - TaskState.input_required if user clarification is needed.
             - TaskState.completed once the final MJCF description is ready.
          5. Convert agent outputs into Task artifacts or plain status updates.

        Args:
            context: Request metadata including current task and user message.
            event_queue: Channel to push task status/events back to the server.
        """
        error = self._validate_request(context)
        if error:
            raise ServerError(error=InvalidParamsError())

        query = context.get_user_input()
        task = context.current_task

        # If no active task exists, create one
        if not task:
            task = new_task(context.message)
            event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue, task.id, task.contextId)

        try:
            # Stream responses from the DescriberAgent
            async for item in self.agent.stream(query, task.contextId):
                is_task_complete = item["is_task_complete"]
                require_user_input = item["require_user_input"]

                if not is_task_complete and not require_user_input:
                    # Publish intermediate "working" update
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
                    # Agent requests clarification → pause execution
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
                    # Final result: save structured description as an artifact
                    updater.add_artifact(
                        [Part(root=TextPart(text=content))],
                        name="mjcf_description",
                    )
                    updater.complete()
                    break

        except Exception as e:
            logger.error(f"An error occurred while streaming the response: {e}")
            raise ServerError(error=InternalError()) from e

    def _validate_request(self, context: RequestContext) -> bool:
        """
        Validate the incoming request.

        Returns:
            False if the request is valid (no errors).
            Could be extended later for schema or input validation.
        """
        return False

    async def cancel(
        self, request: RequestContext, event_queue: EventQueue
    ) -> Task | None:
        """
        Cancel an ongoing task.

        Not supported for the DescriberAgent. Always raises error.
        """
        raise ServerError(error=UnsupportedOperationError())
