from typing import List, Dict, Any, Optional

from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage


# Reusable model client for Ollama
class ModelClient:

    def __init__(
        self,
        model: str = "qwen3:8b",
        temperature: float = 0.0,
        base_url: str = "http://localhost:11434",
    ):
        """
        Initialize the Ollama model and token counters.
        """

        self.model = ChatOllama(
            model=model,
            temperature=temperature,
            base_url=base_url,
        )

        # Cumulative statistics for the conversation
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.turn_count = 0


    def _convert_messages(
        self,
        messages: List[Dict[str, str]]
    ):
        """
        Convert simple role/content dictionaries
        into LangChain message objects.
        """

        converted_messages = []

        for message in messages:

            role = message.get("role", "")
            content = message.get("content", "")

            if role == "system":
                converted_messages.append(
                    SystemMessage(content=content)
                )

            elif role == "assistant":
                converted_messages.append(
                    AIMessage(content=content)
                )

            else:
                converted_messages.append(
                    HumanMessage(content=content)
                )

        return converted_messages


    def _get_token_usage(
        self,
        response
    ):
        """
        Read input and output token counts
        returned by the Ollama/LangChain response.
        """

        input_tokens = 0
        output_tokens = 0

        # Newer LangChain versions usually store
        # token counts inside usage_metadata.
        usage = getattr(
            response,
            "usage_metadata",
            None
        )

        if usage:

            input_tokens = usage.get(
                "input_tokens",
                0
            )

            output_tokens = usage.get(
                "output_tokens",
                0
            )

        # Fallback in case token information
        # is stored in response_metadata instead.
        if input_tokens == 0 and output_tokens == 0:

            metadata = getattr(
                response,
                "response_metadata",
                {}
            )

            input_tokens = metadata.get(
                "prompt_eval_count",
                0
            )

            output_tokens = metadata.get(
                "eval_count",
                0
            )

        return input_tokens, output_tokens


    def complete(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Send conversation messages to the model.

        Stable interface required by the assignment:
        complete(messages, tools=None)
        """

        # Convert dictionaries into LangChain messages
        converted_messages = self._convert_messages(
            messages
        )

        # The assignment interface includes tools.
        # This homework does not require tool calling yet.
        if tools:
            model = self.model.bind_tools(tools)
        else:
            model = self.model

        # Send the request to Ollama
        response = model.invoke(
            converted_messages
        )

        # Get token usage for this turn
        input_tokens, output_tokens = (
            self._get_token_usage(response)
        )

        total_tokens = (
            input_tokens + output_tokens
        )

        # Update cumulative counters
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.turn_count += 1

        return {
            "content": response.content,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        }


    def get_stats(self) -> Dict[str, int]:
        """
        Return cumulative token and turn statistics.
        """

        return {
            "turn_count": self.turn_count,
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "total_tokens": (
                self.total_input_tokens
                + self.total_output_tokens
            ),
        }