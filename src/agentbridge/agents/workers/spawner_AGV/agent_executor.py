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
from agent import SpawnerAGVSDFAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SpawnerAGVSDFAgentExecutor(AgentExecutor):
    """
    Executor for the Spawner AGV (SDF World) Agent.

    Responsibilities:
      - Orchestrates execution of the SpawnerAGVSDFAgent.
      - Translates agent outputs into A2A task updates and artifacts.
      - Handles streaming responses, intermediate updates, and task completion.
    """

    def __init__(self):
        self.agent = SpawnerAGVSDFAgent()

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """
        Main execution loop for the Spawner AGV agent.

        Steps:
          1. Validate request context.
          2. Ensure a task object exists (create if missing).
          3. Stream results from the agent and translate them into task updates.
          4. Handle three types of agent outputs:
             - Ongoing progress updates (TaskState.working).
             - Requests for user input (TaskState.input_required).
             - Final results (artifacts + TaskState.completed).
        """
        error = self._validate_request(context)
        if error:
            raise ServerError(error=InvalidParamsError())

        query = context.get_user_input()
        task = context.current_task
        if not task:
            task = new_task(context.message)
            event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue, task.id, task.contextId)

        try:
            async for item in self.agent.stream(query, task.contextId):
                is_task_complete = item["is_task_complete"]
                require_user_input = item["require_user_input"]

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

                else:
                    # Task completed successfully -> add artifact and mark done
                    updater.add_artifact(
                        [Part(root=TextPart(text=content))],
                        name="gazebo_spawn",
                    )
                    updater.complete()
                    break

        except Exception as e:
            logger.error(f"An error occurred while streaming the response: {e}")
            raise ServerError(error=InternalError()) from e

    def _validate_request(self, context: RequestContext) -> bool:
        """
        Placeholder for request validation.
        Returns True if request is invalid, False otherwise.
        """
        return False

    async def cancel(
        self, request: RequestContext, event_queue: EventQueue
    ) -> Task | None:
        """
        Cancel is not supported for this agent.
        Always raises UnsupportedOperationError.
        """
        raise ServerError(error=UnsupportedOperationError())
