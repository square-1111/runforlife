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

from runforlife.skills.registry import SkillRegistry

SYSTEM_PROMPT = """\
You are RunForLife Coach, a running and Hyrox training assistant for two athletes:
- Tezuesh Varshney (male)
- Kakul Shrivastava (female)

They are training for:
- 300 individual running days each in 2026 (currently ~10 days behind as of March 25)
- Hyrox Mixed Doubles (next race: early April 2026, then September 2026)
- General VO2 max and running improvement

Context:
- Both are software engineers (sedentary jobs)
- Weight training 4x/week (1 session is Hyrox station work)
- Prefer 6 days/week running
- Garmin Forerunner 165 each
- Sleep around 1 AM, dinner by 9 PM

Rules:
1. Always authenticate with Garmin (garmin_auth) before fetching any data.
2. Use actual data — never guess numbers.
3. Be specific with paces, distances, heart rates.
4. Consider both athletes unless asked about one.
5. Be concise and actionable.
"""


class Agent:
    """
    A simple tool-use agent powered by Claude.

    This follows Anthropic's recommended pattern:
    - Send messages with tool definitions
    - When Claude returns tool_use, execute and send results back
    - Loop until Claude returns end_turn
    """

    def __init__(self, registry: SkillRegistry, model: str = "claude-sonnet-4-20250514") -> None:
        self.client = Anthropic()
        self.registry = registry
        self.model = model
        self.conversation: list[dict] = []

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
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=self.registry.get_tool_definitions(),
                messages=self.conversation,
            )

            # Add Claude's response to conversation history
            self.conversation.append({
                "role": "assistant",
                "content": response.content,
            })

            # ── DECISION POINT ──
            # This is where the "agent" part happens.
            # Claude tells us what it wants to do via stop_reason.

            if response.stop_reason == "end_turn":
                # Claude is done — extract and return text
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
