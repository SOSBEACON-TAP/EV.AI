"""
core/brain.py
--------------
The AI "brain" — turns user text into a response using a configured LLM
provider, chosen via AI_PROVIDER in .env (anthropic, gemini, groq, openai/ChatGPT,
openrouter, deepseek, mistral, xai, or custom for any OpenAI-compatible server).

Stage 4 adds tool calling: if a ToolRouter is passed in, the brain tells
the model what tools exist, and when the model wants to use one, runs it
via the router and feeds the result back for a final natural-language
answer. The tool-call back-and-forth is ephemeral per request — only the
final user-facing reply gets added to the short-term conversation
history, keeping that history simple plain text either way.

Provider SDKs are imported lazily (inside __init__/ask), not at module
level — so if only one provider's package is installed, the other
provider simply isn't usable instead of the whole app failing to start.
"""

import json

from config import settings, OPENAI_COMPATIBLE
from core.router import ToolRouter, ToolError
from core.modes import Mode, PROMPT_ADDITIONS, MAX_TOKENS


class BrainError(Exception):
    """Raised when the AI brain cannot produce a response (bad key, no
    network, rate limited, missing package, etc). Callers should catch
    this and show a friendly message rather than crashing — see
    ui/main_window.py."""


SYSTEM_PROMPT = (
    "You are EV AI, running locally on the user's Windows PC. You were invented "
    "by Shri Nikil Prakash — if anyone asks who invented, created or made you, "
    "answer that you were invented by Shri Nikil Prakash. Talk like a "
    "close friend who happens to be great with computers — not like a "
    "formal assistant or a customer-support bot. Casual, warm, a little "
    "playful when it fits; use contractions, keep it real, don't pad "
    "replies with corporate-sounding filler ('I'd be happy to...', 'Let "
    "me know if there's anything else...'). Keep replies SHORT — a "
    "sentence or two for most things, since they're often read aloud via "
    "text-to-speech. No long lists, no markdown, nothing awkward to hear "
    "spoken out loud. You have a set of tools available — use them when "
    "they'd answer the request instead of guessing. For anything you "
    "don't have a tool for, say so plainly (still casually) instead of "
    "pretending to do it. "
    "You can remember durable facts about the user with the remember "
    "tool (preferences, project info, custom commands — never "
    "passwords, API keys, or other credentials; the tool will refuse "
    "those anyway), look them up with recall, and forget or clear_memory "
    "when asked. Use recall proactively when a request seems to "
    "reference something the user may have told you before, rather "
    "than asking them to repeat it. "
    "Some tools require confirmation: calling them without confirmed=true "
    "returns a result like {'confirmation_required': true, 'message': ...} "
    "instead of actually doing anything. When that happens, relay the "
    "message to the user in your own words and wait for them to "
    "explicitly agree before calling that tool again with confirmed=true "
    "— never claim an action succeeded when the tool result shows "
    "confirmation_required or an error. "
    "You can also automate multi-step routines: save_task_chain stores a "
    "named sequence of tool calls (e.g. 'start work' opening several apps "
    "at once) for run_task_chain to replay later — never include "
    "confirmed=true for a sensitive step in a saved chain unless the user "
    "has clearly said that step should run unattended every time, since a "
    "chain runs without a chance to ask again. schedule_recurring sets up "
    "a daily or weekly reminder/action that persists across restarts; use "
    "set_timer instead for a one-off 'in N seconds/minutes' reminder. "
    "type_text/press_key and the browser_* tools act immediately, no "
    "confirmation needed — they're the direct equivalent of the user "
    "typing/clicking themselves. The browser_* tools control one ongoing "
    "browser window across multiple commands (search, then click, then "
    "scroll, etc.) — keep using them on the same session rather than "
    "re-opening a new page for each step of a multi-step browsing request. "
    "open_whatsapp_web and send_whatsapp_message are different tools: "
    "open_whatsapp_web just opens the WhatsApp Web page in the user's "
    "regular default browser for them to use by hand, and cannot send "
    "anything. Whenever the user wants a message actually sent to someone "
    "on WhatsApp, always use send_whatsapp_message, never open_whatsapp_web. "
    "The very first time send_whatsapp_message is ever used, it needs a "
    "QR code scanned in the browser window it opens (phone: WhatsApp -> "
    "Settings/kebab menu -> Linked Devices -> Link a Device) before it can "
    "do anything else — mention this to the user right when you ask them "
    "to confirm sending, not only after it times out, so they know to have "
    "their phone ready. After that first scan it stays logged in and this "
    "step isn't needed again."
)

MAX_TOOL_ITERATIONS = 5  # hard cap so a confused model can't loop forever


class Brain:
    def __init__(self, api_key: str | None = None, model: str | None = None,
                 history_limit: int = 10, provider: str | None = None,
                 router: ToolRouter | None = None):
        self.provider = (provider or settings.AI_PROVIDER or "anthropic").lower()
        self.model = model or settings.AI_MODEL
        self.history_limit = history_limit
        self._history: list[dict] = []  # short-term conversation context (plain text only)
        self.mode: Mode = Mode.NORMAL
        self._router = router

        self._api_key = api_key or settings.AI_API_KEY
        self._client = None
        self._init_error: str | None = None

        if not self._api_key:
            return  # stays unconfigured — is_configured will be False

        try:
            if self.provider == "gemini":
                from google import genai
                self._client = genai.Client(api_key=self._api_key)
            elif self.provider == "anthropic":
                import anthropic
                self._client = anthropic.Anthropic(api_key=self._api_key)
            elif self.provider == "groq":
                from groq import Groq
                self._client = Groq(api_key=self._api_key)
            elif self.provider in OPENAI_COMPATIBLE:
                import openai
                base_url = settings.AI_BASE_URL or OPENAI_COMPATIBLE[self.provider][0] or None
                if self.provider == "custom" and not base_url:
                    self._init_error = "AI_PROVIDER=custom needs AI_BASE_URL (e.g. http://localhost:11434/v1)."
                else:
                    self._client = openai.OpenAI(api_key=self._api_key, base_url=base_url)
            else:
                known = ", ".join(["anthropic", "gemini", "groq", *OPENAI_COMPATIBLE])
                self._init_error = f"Unknown AI_PROVIDER '{self.provider}' — use one of: {known}."
        except ImportError:
            self._init_error = (
                f"The package for AI_PROVIDER='{self.provider}' isn't installed. "
                "Run: pip install -r requirements.txt"
            )

    @property
    def is_configured(self) -> bool:
        return self._client is not None

    @property
    def init_error(self) -> str | None:
        """Why the brain isn't configured (missing package, unknown
        provider), if that's the reason — None if it's simply missing an
        API key, or if it initialized fine."""
        return self._init_error

    def set_mode(self, mode: Mode) -> None:
        self.mode = mode

    def _effective_system_prompt(self) -> str:
        try:
            from core.personality import prompt_addition
            extra = prompt_addition()
        except Exception:
            extra = ""
        try:
            from core import user_prefs
            if not user_prefs.get("confirm_before_sending"):
                extra += ("\n\nSending: the user has turned OFF send confirmations. When they ask you to send an "
                          "email or a WhatsApp message, do it immediately with confirmed=true — do not ask "
                          "'are you sure?' first. Only ask if the recipient or the message itself is missing or ambiguous.")
        except Exception:
            pass
        try:
            from core import convo_memory
            from tools.memory import get_store
            extra += convo_memory.prompt_block(get_store())
        except Exception:
            try:
                from core import convo_memory
                extra += convo_memory.prompt_block()
            except Exception:
                pass
        return SYSTEM_PROMPT + PROMPT_ADDITIONS.get(self.mode, "") + extra

    def _effective_max_tokens(self) -> int:
        return MAX_TOKENS.get(self.mode, 400)

    def reset_context(self) -> None:
        # Keep what was said: fold the whole short-term window into long-term memory first.
        try:
            from core import convo_memory
            convo_memory.remember_dropped(list(self._history))
        except Exception:
            pass
        self._history.clear()

    def ask(self, user_text: str) -> str:
        """Send user_text plus recent history to the model, return its
        final reply as plain text (after running any tool calls it made
        along the way). Raises BrainError on any failure."""
        if self._init_error:
            raise BrainError(self._init_error)
        if not self.is_configured:
            raise BrainError(
                "No AI_API_KEY configured. Add one to your .env file to enable EV's AI brain."
            )

        self._history.append({"role": "user", "content": user_text})
        self._trim_history()

        try:
            if self.provider == "gemini":
                reply_text = self._ask_gemini()
            elif self.provider == "groq" or self.provider in OPENAI_COMPATIBLE:
                reply_text = self._ask_groq()
            else:
                reply_text = self._ask_anthropic()
        except BrainError:
            raise
        except Exception as e:
            raise BrainError(f"Unexpected AI error: {e}") from e

        self._history.append({"role": "assistant", "content": reply_text})
        self._trim_history()
        return reply_text

    # ------------------------------------------------------------------
    # Anthropic (Claude)
    # ------------------------------------------------------------------
    def _execute_tool(self, name, args):
        """Runs a tool; in Jarvis mode anything outside system monitoring is refused."""
        if self.mode == Mode.JARVIS:
            from core.modes import JARVIS_TOOLS
            if name not in JARVIS_TOOLS:
                raise ToolError("Jarvis only monitors the system. Switch back to EV for that.")
        return self._router.execute(name, args)

    def _visible_tools(self):
        """Every tool, except in Jarvis mode where only system-monitoring tools are offered."""
        tools = self._router.list_tools()
        if self.mode == Mode.JARVIS:
            from core.modes import JARVIS_TOOLS
            tools = [t for t in tools if t.name in JARVIS_TOOLS]
        return tools

    def _anthropic_tool_schemas(self) -> list[dict]:
        schemas = []
        for tool in self._visible_tools():
            schemas.append({
                "name": tool.name,
                "description": tool.description,
                "input_schema": {
                    "type": "object",
                    "properties": tool.parameters,
                    "required": tool.required,
                },
            })
        return schemas

    def _ask_anthropic(self) -> str:
        import anthropic

        messages = [{"role": m["role"], "content": m["content"]} for m in self._history]
        tools = self._anthropic_tool_schemas() if self._router else None

        for _ in range(MAX_TOOL_ITERATIONS):
            kwargs = dict(model=self.model, max_tokens=self._effective_max_tokens(),
                          system=self._effective_system_prompt(), messages=messages)
            if tools:
                kwargs["tools"] = tools

            try:
                response = self._client.messages.create(**kwargs)
            except anthropic.AuthenticationError as e:
                raise BrainError("Invalid API key — check AI_API_KEY in your .env file.") from e
            except anthropic.APIConnectionError as e:
                raise BrainError("Could not reach the AI service — check your internet connection.") from e
            except anthropic.RateLimitError as e:
                raise BrainError("AI service rate limit reached — try again in a moment.") from e
            except anthropic.APIStatusError as e:
                raise BrainError(f"AI service error ({e.status_code}).") from e

            if response.stop_reason != "tool_use":
                parts = [b.text for b in response.content if getattr(b, "type", None) == "text"]
                return "".join(parts).strip() or "..."

            # Model wants to call one or more tools — run them and report back.
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if getattr(block, "type", None) != "tool_use":
                    continue
                try:
                    result = self._execute_tool(block.name, block.input or {})
                except ToolError as e:
                    result = {"error": str(e)}
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result),
                })
            messages.append({"role": "user", "content": tool_results})

        raise BrainError("EV got stuck calling tools repeatedly — try rephrasing your request.")

    # ------------------------------------------------------------------
    # Groq
    # ------------------------------------------------------------------
    # Groq's API is OpenAI-compatible, so tool calling uses the same
    # {"type": "function", "function": {...}} shape as OpenAI, with tool
    # results sent back as role="tool" messages tagged by tool_call_id.
    def _openai_style_tool_schemas(self) -> list[dict]:
        schemas = []
        for tool in self._visible_tools():
            schemas.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": {
                        "type": "object",
                        "properties": tool.parameters,
                        "required": tool.required,
                    },
                },
            })
        return schemas

    def _sdk(self):
        """The SDK module whose exception classes match self._client."""
        if self.provider == "groq":
            import groq
            return groq
        import openai
        return openai

    def _ask_groq(self) -> str:
        # Serves Groq and every OpenAI-style provider (same API shape).
        groq = self._sdk()

        messages = [{"role": "system", "content": self._effective_system_prompt()}]
        messages += [{"role": m["role"], "content": m["content"]} for m in self._history]
        tools = self._openai_style_tool_schemas() if self._router else None

        for _ in range(MAX_TOOL_ITERATIONS):
            kwargs = dict(model=self.model, messages=messages, max_tokens=self._effective_max_tokens())
            if tools:
                kwargs["tools"] = tools
            # Reasoning models (gpt-oss) think before answering, which is the main delay.
            # "low" keeps replies quick; Deep Thinking mode keeps more reasoning.
            if "gpt-oss" in (self.model or "").lower() and not getattr(self, "_no_effort", False):
                kwargs["reasoning_effort"] = "medium" if self.mode == Mode.DEEP_THINKING else "low"

            try:
                try:
                    response = self._client.chat.completions.create(**kwargs)
                except groq.BadRequestError:
                    if "reasoning_effort" not in kwargs:
                        raise
                    self._no_effort = True      # this provider rejects the option; stop sending it
                    kwargs.pop("reasoning_effort")
                    response = self._client.chat.completions.create(**kwargs)
            except groq.AuthenticationError as e:
                raise BrainError("Invalid API key — check AI_API_KEY in your .env file.") from e
            except groq.APIConnectionError as e:
                raise BrainError("Could not reach the AI service — check your internet connection.") from e
            except groq.RateLimitError as e:
                raise BrainError("AI service rate limit reached — try again in a moment.") from e
            except groq.APIStatusError as e:
                raise BrainError(f"AI service error ({e.status_code}).") from e

            message = response.choices[0].message
            tool_calls = getattr(message, "tool_calls", None)

            if not tool_calls:
                return (message.content or "...").strip()

            # Model wants to call one or more tools — run them and report back.
            messages.append({
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in tool_calls
                ],
            })
            for tc in tool_calls:
                try:
                    arguments = json.loads(tc.function.arguments or "{}")
                    result = self._execute_tool(tc.function.name, arguments)
                except json.JSONDecodeError:
                    result = {"error": "The model sent invalid arguments for this tool."}
                except ToolError as e:
                    result = {"error": str(e)}
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result)})

        raise BrainError("EV got stuck calling tools repeatedly — try rephrasing your request.")

    # ------------------------------------------------------------------
    # Gemini
    # ------------------------------------------------------------------
    def _gemini_tool_declarations(self):
        from google.genai import types

        json_to_gemini_type = {
            "string": "STRING",
            "integer": "INTEGER",
            "number": "NUMBER",
            "boolean": "BOOLEAN",
            "array": "ARRAY",
            "object": "OBJECT",
        }

        declarations = []
        for tool in self._visible_tools():
            properties = {}
            for key, spec in (tool.parameters or {}).items():
                gemini_type = json_to_gemini_type.get(spec.get("type", "string"), "STRING")
                properties[key] = types.Schema(type=gemini_type, description=spec.get("description", ""))
            declarations.append(types.FunctionDeclaration(
                name=tool.name,
                description=tool.description,
                parameters=types.Schema(type="OBJECT", properties=properties, required=tool.required or []),
            ))
        return declarations

    def _ask_gemini(self) -> str:
        from google.genai import types

        contents = []
        for msg in self._history:
            role = "model" if msg["role"] == "assistant" else "user"
            contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))

        config_kwargs = dict(system_instruction=self._effective_system_prompt(),
                              max_output_tokens=self._effective_max_tokens())
        if self._router:
            config_kwargs["tools"] = [types.Tool(function_declarations=self._gemini_tool_declarations())]

        for _ in range(MAX_TOOL_ITERATIONS):
            try:
                response = self._client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=types.GenerateContentConfig(**config_kwargs),
                )
            except Exception as e:
                raise self._map_gemini_error(e)

            candidate = response.candidates[0] if response.candidates else None
            function_call = None
            if candidate is not None:
                for part in candidate.content.parts:
                    if getattr(part, "function_call", None):
                        function_call = part.function_call
                        break

            if function_call is None:
                return (getattr(response, "text", None) or "...").strip()

            # Model wants to call a tool — run it and report the result back.
            contents.append(candidate.content)
            try:
                result = self._execute_tool(function_call.name, dict(function_call.args or {}))
            except ToolError as e:
                result = {"error": str(e)}
            contents.append(types.Content(
                role="user",
                parts=[types.Part.from_function_response(name=function_call.name, response=result)],
            ))

        raise BrainError("EV got stuck calling tools repeatedly — try rephrasing your request.")

    @staticmethod
    def _map_gemini_error(e: Exception) -> BrainError:
        text = str(e).lower()
        if "not_found" in text or "not found" in text or "404" in text:
            return BrainError("The configured Gemini model isn't available — check AI_MODEL in your .env file.")
        if "api_key_invalid" in text or "api key not valid" in text or "unauthenticated" in text:
            return BrainError("Invalid API key — check AI_API_KEY in your .env file.")
        if "quota" in text or "rate" in text or "resource_exhausted" in text:
            return BrainError("AI service rate limit reached — try again in a moment.")
        return BrainError(f"AI service error: {e}")

    # ------------------------------------------------------------------
    # Observation mode: one-off vision calls, kept OUT of self._history
    # (this is a background glance, not part of the conversation) and
    # using AI_VISION_MODEL rather than self.model, since not every chat
    # model is also vision-capable (notably on Groq).
    # ------------------------------------------------------------------
    OBSERVE_PROMPT = (
        "You are glancing at the user's screen ONCE to see if there's something genuinely "
        "worth proactively mentioning — a clear error message, a typo in something important "
        "like an email or a form, a stuck/confusing state, or an obvious natural opportunity "
        "to help. Most of the time there will be nothing worth saying — normal browsing or "
        "work in progress is NOT noteworthy. If there is nothing worth mentioning, respond "
        "with EXACTLY the single word: NOTHING. Otherwise, respond with ONE short, natural "
        "spoken sentence, as a helpful friend glancing over might say out loud. Never describe "
        "everything on screen — only speak up if it is genuinely useful."
    )

    def observe_screen(self, image_png_bytes: bytes) -> str | None:
        """Look at one screenshot and return a short comment, or None if
        there's nothing worth saying. Raises BrainError on failure."""
        if self._init_error:
            raise BrainError(self._init_error)
        if not self.is_configured:
            raise BrainError("No AI_API_KEY configured.")

        try:
            if self.provider == "gemini":
                text = self._observe_gemini(image_png_bytes)
            elif self.provider == "groq" or self.provider in OPENAI_COMPATIBLE:
                text = self._observe_groq(image_png_bytes)
            else:
                text = self._observe_anthropic(image_png_bytes)
        except BrainError:
            raise
        except Exception as e:
            raise BrainError(f"Unexpected AI error: {e}") from e

        text = (text or "").strip()
        return None if text.upper() == "NOTHING" else text

    def _observe_anthropic(self, image_png_bytes: bytes, prompt: str | None = None,
                           max_tokens: int = 120, mime: str = "image/png") -> str:
        import anthropic
        import base64

        b64 = base64.b64encode(image_png_bytes).decode("ascii")
        try:
            response = self._client.messages.create(
                model=settings.AI_VISION_MODEL,
                max_tokens=max_tokens,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}},
                        {"type": "text", "text": prompt or self.OBSERVE_PROMPT},
                    ],
                }],
            )
        except anthropic.AuthenticationError as e:
            raise BrainError("Invalid API key — check AI_API_KEY in your .env file.") from e
        except anthropic.APIConnectionError as e:
            raise BrainError("Could not reach the AI service — check your internet connection.") from e
        except anthropic.RateLimitError as e:
            raise BrainError("AI service rate limit reached — try again in a moment.") from e
        except anthropic.APIStatusError as e:
            raise BrainError(f"AI service error ({e.status_code}).") from e

        parts = [b.text for b in response.content if getattr(b, "type", None) == "text"]
        return "".join(parts)

    def _observe_gemini(self, image_png_bytes: bytes, prompt: str | None = None,
                        max_tokens: int = 120, mime: str = "image/png") -> str:
        from google.genai import types

        content = types.Content(role="user", parts=[
            types.Part.from_bytes(data=image_png_bytes, mime_type=mime),
            types.Part(text=prompt or self.OBSERVE_PROMPT),
        ])
        try:
            response = self._client.models.generate_content(
                model=settings.AI_VISION_MODEL,
                contents=[content],
                config=types.GenerateContentConfig(max_output_tokens=max_tokens),
            )
        except Exception as e:
            raise self._map_gemini_error(e)
        return getattr(response, "text", None) or ""

    def _observe_groq(self, image_png_bytes: bytes, prompt: str | None = None,
                      max_tokens: int = 120, mime: str = "image/png") -> str:
        groq = self._sdk()
        import base64

        b64 = base64.b64encode(image_png_bytes).decode("ascii")
        try:
            response = self._client.chat.completions.create(
                model=settings.AI_VISION_MODEL,
                max_tokens=max_tokens,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt or self.OBSERVE_PROMPT},
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    ],
                }],
            )
        except groq.AuthenticationError as e:
            raise BrainError("Invalid API key — check AI_API_KEY in your .env file.") from e
        except groq.APIConnectionError as e:
            raise BrainError("Could not reach the AI service — check your internet connection.") from e
        except groq.RateLimitError as e:
            raise BrainError("AI service rate limit reached — try again in a moment.") from e
        except groq.APIStatusError as e:
            raise BrainError(f"AI service error ({e.status_code}).") from e

        return response.choices[0].message.content or ""

    IMAGE_PROMPT = (
        "The user shared an image and asked about it. Answer their question directly and "
        "concisely. If it shows text, an error message, a diagram, a homework problem or an "
        "electronics/circuit setup, read it carefully and explain or help fix it step by step. "
        "Say plainly if something is unreadable."
    )

    def ask_about_image(self, image_bytes: bytes, mime: str, question: str, label: str = "an image") -> str:
        """Answer a question about an image the user chose to share, with
        the vision model. The exchange is added to the short-term history
        (as text) so follow-up questions work. Raises BrainError on failure."""
        if self._init_error:
            raise BrainError(self._init_error)
        if not self.is_configured:
            raise BrainError("No AI_API_KEY configured.")
        question = (question or "").strip() or "Explain what this shows."
        prompt = f"{self.IMAGE_PROMPT}\n\nUser's question: {question}"
        try:
            if self.provider == "gemini":
                text = self._observe_gemini(image_bytes, prompt, 900, mime)
            elif self.provider == "groq" or self.provider in OPENAI_COMPATIBLE:
                text = self._observe_groq(image_bytes, prompt, 900, mime)
            else:
                text = self._observe_anthropic(image_bytes, prompt, 900, mime)
        except BrainError:
            raise
        except Exception as e:
            raise BrainError(f"Unexpected AI error: {e}") from e
        text = (text or "").strip() or "I couldn't make anything out of that image."
        self._history.append({"role": "user", "content": f"[Shared {label}] {question}"})
        self._history.append({"role": "assistant", "content": text})
        self._trim_history()
        return text

    def _trim_history(self) -> None:
        # Bounded short-term context, not a full transcript — keeps
        # token usage predictable on long-running sessions.
        if len(self._history) > self.history_limit:
            dropped = self._history[:-self.history_limit]
            self._history = self._history[-self.history_limit:]
            try:
                from core import convo_memory
                convo_memory.remember_dropped(dropped)
            except Exception:
                pass
