"""
THE AGENT LOOP
===============
This is the heart of everything. This file is what makes an LLM into an agent.

A chatbot:  user → LLM → response. Done.
An agent:   user → LLM → "I need a tool" → run tool → give result to LLM →
            "I need another tool" → run → ... → "I can answer now" → response

The LLM DECIDES what to do. Your code just:
  1. Sends messages to the LLM
  2. Checks if the LLM wants to use a tool (stop_reason == "tool_use")
  3. Executes the tool
  4. Sends the result back
  5. Repeats until the LLM says it's done (stop_reason == "end_turn")

That's literally all an agent is. Everything else — memory, planning,
multi-agent, self-evolution — is built on top of this loop.

Anthropic's "Building Effective Agents" guide says:
  "Agents can be built with simple, composable patterns."
  "The most important thing is to keep the tool definitions clear."
"""

import json

from anthropic import Anthropic

from runforlife.config import MODEL
from runforlife.skills.registry import SkillRegistry

_DEFAULT_SYSTEM_PROMPT = """\
You are RunForLife Coach, a running and Hyrox training assistant.

Rules:
1. Always authenticate with Garmin (garmin_auth) before fetching any data.
2. Use actual data — never guess numbers.
3. Be specific with paces, distances, heart rates.
4. Be concise and actionable.
"""


class Agent:
    """
    A simple tool-use agent powered by Claude.

    This follows Anthropic's recommended pattern:
    - Send messages with tool definitions
    - When Claude returns tool_use, execute and send results back
    - Loop until Claude returns end_turn
    """

    def __init__(
        self,
        registry: SkillRegistry,
        model: str = MODEL,
        system_prompt: str = _DEFAULT_SYSTEM_PROMPT,
        initial_conversation: list[dict] | None = None,
        thinking_budget: int = 0,
    ) -> None:
        self.client = Anthropic()
        self.registry = registry
        self.model = model
        self.system_prompt = system_prompt
        self.conversation: list[dict] = list(initial_conversation or [])
        self.thinking_budget = thinking_budget

    def chat(self, user_message: str) -> str:
        """
        THE AGENT LOOP — the most important function in this entire project.

        Read this carefully:

        Step 1: Add user message to conversation history
        Step 2: Call Claude with conversation + tool definitions
        Step 3: Check stop_reason:
                - "end_turn" → Claude is done, return the text
                - "tool_use" → Claude wants to call a tool
        Step 4: If tool_use:
                - Execute the tool
                - Add result to conversation
                - Go back to Step 2

        That's it. Every agent framework wraps this loop in different
        abstractions, but this is what's actually happening.
        """
        self.conversation.append({
            "role": "user",
            "content": user_message,
        })

        while True:
            # Call Claude with all available tools
            create_kwargs: dict = dict(
                model=self.model,
                max_tokens=16000 if self.thinking_budget else 4096,
                system=self.system_prompt,
                tools=self.registry.get_tool_definitions(),
                messages=self.conversation,
            )
            if self.thinking_budget:
                create_kwargs["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": self.thinking_budget,
                }

            response = self.client.messages.create(**create_kwargs)

            # Add Claude's response to conversation history
            self.conversation.append({
                "role": "assistant",
                "content": response.content,
            })

            # ── DECISION POINT ──
            # This is where the "agent" part happens.
            # Claude tells us what it wants to do via stop_reason.

            if response.stop_reason == "end_turn":
                # Print thinking blocks to console so the user can see reasoning
                for block in response.content:
                    if block.type == "thinking":
                        print(f"\n  [thinking]\n{block.thinking}\n  [/thinking]\n")
                # Return only the final text
                return "\n".join(
                    block.text for block in response.content
                    if block.type == "text"
                )

            # Claude wants to use tools — execute each one
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue

                print(f"  >> skill: {block.name}({json.dumps(block.input, default=str)})")

                result = self.registry.execute(block.name, block.input)

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, default=str),
                })

            # Send tool results back to Claude
            # Claude will see these and either call more tools or respond
            self.conversation.append({
                "role": "user",
                "content": tool_results,
            })
            # Loop continues — back to calling Claude

    def reset(self) -> None:
        """Clear conversation history. Start fresh."""
        self.conversation.clear()
