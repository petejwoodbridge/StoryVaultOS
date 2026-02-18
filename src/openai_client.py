"""
StoryVault OpenAI Client
Wraps OpenAI chat completions with token tracking, cost estimation,
and retry logic.
"""

import time

try:
    from openai import OpenAI, RateLimitError, APIError, APIConnectionError
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

# ------------------------------------------------------------------ #
# Pricing table (USD per token, as of mid-2024)
# ------------------------------------------------------------------ #

PRICING = {
    "gpt-4o-mini": {
        "prompt":     0.150 / 1_000_000,   # $0.150 / 1M input tokens
        "completion": 0.600 / 1_000_000,   # $0.600 / 1M output tokens
    },
    "gpt-4o": {
        "prompt":     2.50  / 1_000_000,
        "completion": 10.00 / 1_000_000,
    },
    "gpt-4-turbo": {
        "prompt":     10.00 / 1_000_000,
        "completion": 30.00 / 1_000_000,
    },
}


class OpenAIClientError(Exception):
    pass


class OpenAIClient:
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        if not OPENAI_AVAILABLE:
            raise OpenAIClientError(
                "openai package not installed. Run: pip install openai"
            )
        if not api_key:
            raise OpenAIClientError(
                "No API key provided. Set OPENAI_API_KEY or run: "
                "python storyvault.py set-key <key>"
            )
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.last_usage: dict | None = None

    # ------------------------------------------------------------------ #
    # Public interface
    # ------------------------------------------------------------------ #

    def complete(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        max_retries: int = 3,
    ) -> tuple[str, dict]:
        """
        Send chat completion request.

        Returns:
            (content: str, usage: dict)
            usage keys: prompt_tokens, completion_tokens, total_tokens, cost
        """
        last_error = None

        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return self._extract_result(response)

            except RateLimitError as e:
                last_error = e
                wait = 2 ** (attempt + 1)
                time.sleep(wait)

            except APIConnectionError as e:
                last_error = e
                if attempt < max_retries - 1:
                    time.sleep(2)

            except APIError as e:
                last_error = e
                if attempt < max_retries - 1:
                    time.sleep(1)
                else:
                    raise OpenAIClientError(f"OpenAI API error: {e}") from e

        raise OpenAIClientError(
            f"Request failed after {max_retries} attempts: {last_error}"
        )

    def complete_stream(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ):
        """
        Stream chat completion. Yields str chunks, then a final dict with usage.

        Usage pattern:
            for chunk in client.complete_stream(messages):
                if isinstance(chunk, str):
                    print(chunk, end='', flush=True)
                else:
                    usage = chunk  # dict with token counts + cost
        """
        stream = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            stream_options={"include_usage": True},
        )

        prompt_t = 0
        completion_t = 0

        for event in stream:
            # Yield text chunks
            if event.choices:
                delta = event.choices[0].delta
                if delta and delta.content:
                    yield delta.content

            # Capture usage from the final chunk
            if event.usage:
                prompt_t     = event.usage.prompt_tokens
                completion_t = event.usage.completion_tokens

        cost = self._calculate_cost(prompt_t, completion_t)
        usage = {
            "prompt_tokens":     prompt_t,
            "completion_tokens": completion_t,
            "total_tokens":      prompt_t + completion_t,
            "cost":              cost,
        }
        self.last_usage = usage
        yield usage

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _extract_result(self, response) -> tuple[str, dict]:
        content = response.choices[0].message.content or ""
        usage_obj = response.usage
        prompt_t     = usage_obj.prompt_tokens
        completion_t = usage_obj.completion_tokens
        cost         = self._calculate_cost(prompt_t, completion_t)

        usage = {
            "prompt_tokens":     prompt_t,
            "completion_tokens": completion_t,
            "total_tokens":      usage_obj.total_tokens,
            "cost":              cost,
        }
        self.last_usage = usage
        return content, usage

    def _calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        pricing = PRICING.get(self.model, PRICING["gpt-4o-mini"])
        return (
            prompt_tokens     * pricing["prompt"] +
            completion_tokens * pricing["completion"]
        )
