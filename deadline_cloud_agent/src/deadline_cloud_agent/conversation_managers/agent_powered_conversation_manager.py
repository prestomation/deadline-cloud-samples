"""Summarizing conversation history management with configurable options."""

import logging
from typing import List, Optional

from strands.types.content import Message
from strands.agent import Agent
from strands.agent.conversation_manager import ConversationManager


logger = logging.getLogger(__name__)


BASE_SUMMARIZATION_PROMPT = """You are a conversation summarizer. Provide a concise summary of the conversation \
history.

Format Requirements:
- You MUST create a structured and concise summary in bullet-point format.
- You MUST NOT respond conversationally.
- You MUST NOT address the user directly.

Task:
Your task is to create a structured summary document:
- It MUST contain bullet points with key topics and questions covered
- It MUST contain bullet points for any code or technical information shared
- It MUST contain a section of key insights gained
- It MUST format the summary in the third person

Example format:

## Conversation Summary
* Topic 1: Key information
* Topic 2: Key information

"""


class AgentPoweredConversationManager(ConversationManager):

    def __init__(self, summarization_agent: Agent):
        """Initialize the summarizing conversation manager.

        Args:
            agent: Agent
        """
        self.summarization_agent = summarization_agent

    def apply_management(self, agent: "Agent") -> None:
        """Apply management strategy to conversation history.

        For the summarizing conversation manager, no proactive management is performed.
        Summarization only occurs when there's a context overflow that triggers reduce_context.

        Args:
            agent: The agent whose conversation history will be managed.
                The agent's messages list is modified in-place.
        """
        # No proactive management - summarization only happens on context overflow
        pass

    def reduce_context(self, agent: Agent, e: Optional[Exception] = None) -> None:
        """Reduce context using summarization.

        Args:
            agent: The agent whose conversation history will be reduced.
                The agent's messages list is modified in-place.
            e: The exception that triggered the context reduction, if any.

        Raises:
            ContextWindowOverflowException: If the context cannot be summarized.
        """
        # If 'agent' is of type 'Agent' use agent.messages, otherwise use 'agent' as-is
        messages = agent.messages if isinstance(agent, Agent) else agent

        try:

            self.summarization_agent.messages = messages

            result = self.summarization_agent("Please summarize this conversation.")

            summary_message = result.message

            # Replace the summarized messages with the summary
            agent.messages[:] = [summary_message]

        except Exception as summarization_error:
            logger.error("Summarization failed: %s", summarization_error)
            raise summarization_error from e

    def _generate_summary(self, messages: List[Message]) -> Message:
        """Generate a summary of the provided messages.

        Args:
            messages: The messages to summarize.
            agent: The agent instance to use for summarization.

        Returns:
            A message containing the conversation summary.

        Raises:
            Exception: If summary generation fails.
        """
