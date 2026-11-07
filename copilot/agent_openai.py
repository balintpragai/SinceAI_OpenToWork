"""OpenAI-compatible provider (Featherless by default). Same interface and trace as agent.Copilot,
with our own tool-calling loop because the OpenAI API does not execute tools for us."""
import inspect
import json
import os
import re
import typing

from openai import APIConnectionError, APIStatusError, OpenAI

from . import tools
from .agent import Copilot, check_citations, system_prompt

BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.featherless.ai/v1")
MODEL = os.environ.get("FEATHERLESS_MODEL", "Qwen/Qwen3.8-Flash-Next")
FALLBACKS = [m for m in os.environ.get("FEATHERLESS_FALLBACKS", "Qwen/Qwen3-30B-A3B-Instruct-2507").split(",") if m]
MAX_STEPS = 10  # then one forced final answer without tools
MAX_TOOL_CHARS = 20_000  # keep one tool result from crowding the context

_JSON = {int: "integer", float: "number", str: "string", bool: "boolean"}


def _schema(fn) -> dict:
    """OpenAI tool schema from the signature and the 'Args:' section of the docstring."""
    doc = inspect.getdoc(fn) or ""
    arg_docs = dict(re.findall(r"^\s{4}(\w+): (.+(?:\n\s{8,}.+)*)", doc, re.M))
    props, required = {}, []
    for name, p in inspect.signature(fn).parameters.items():
        t = p.annotation
        if typing.get_origin(t) is list:
            prop = {"type": "array", "items": {"type": _JSON.get(typing.get_args(t)[0], "string")}}
        else:
            prop = {"type": _JSON.get(t, "string")}
        if name in arg_docs:
            prop["description"] = " ".join(arg_docs[name].split())
        props[name] = prop
        if p.default is inspect.Parameter.empty:
            required.append(name)
    summary = doc.split("\n    Args:")[0].split("\nArgs:")[0].strip()
    return {"type": "function", "function": {"name": fn.__name__, "description": summary,
                                             "parameters": {"type": "object", "properties": props, "required": required}}}


_THINK = re.compile(r"<think>.*?</think>\s*", re.S)


class OpenAICopilot(Copilot):
    def __init__(self, model: str = MODEL, history: list[tuple[str, str]] | None = None):
        self.client = OpenAI(base_url=BASE_URL, api_key=os.environ["FEATHERLESS_API_KEY"], timeout=120, max_retries=1)
        self.model = model
        self.trace: list[dict] = []
        self.funcs = {f.__name__: self._traced(f) for f in tools.TOOLS}
        self.tool_specs = [_schema(f) for f in tools.TOOLS]
        self.system = system_prompt()
        self.new_chat(history)

    def new_chat(self, history: list[tuple[str, str]] | None = None):
        self.messages = [{"role": "system", "content": self.system}]
        self.messages += [{"role": "assistant" if r == "model" else "user", "content": t} for r, t in (history or []) if t]

    def _complete(self, final: bool = False):
        candidates = [MODEL, *[m for m in FALLBACKS if m != MODEL]]  # primary first on every call, not sticky
        for model in candidates:
            try:
                r = self.client.chat.completions.create(model=model, messages=self.messages, tools=self.tool_specs,
                                                        tool_choice="none" if final else "auto",
                                                        temperature=0.1, max_tokens=4000)
                self.model = model
                return r
            except (APIConnectionError, APIStatusError) as e:
                code = getattr(e, "status_code", 503)
                if code not in (408, 429, 500, 502, 503, 504) or model == candidates[-1]:
                    raise

    def ask(self, question: str, fresh: bool = False) -> dict:
        if fresh:
            self.new_chat()
        self.trace = []
        start = len(self.messages)
        self.messages.append({"role": "user", "content": question})
        usage = {"prompt": 0, "cached": None, "output": 0}
        try:
            for _ in range(MAX_STEPS):
                r = self._complete()
                if r.usage:
                    usage["prompt"] += r.usage.prompt_tokens or 0
                    usage["output"] += r.usage.completion_tokens or 0
                msg = r.choices[0].message
                if not msg.tool_calls:
                    text = _THINK.sub("", msg.content or "").strip()
                    self.messages.append({"role": "assistant", "content": text})
                    break
                self.messages.append({"role": "assistant", "content": msg.content or "",
                                      "tool_calls": [tc.model_dump() for tc in msg.tool_calls]})
                for tc in msg.tool_calls:
                    fn = self.funcs.get(tc.function.name)
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                        result = fn(**args) if fn else {"error": f"unknown tool {tc.function.name}"}
                    except (json.JSONDecodeError, TypeError) as e:  # malformed call: tell the model, let it retry
                        result = {"error": f"bad arguments: {e}"}
                    content = json.dumps(result, default=str)
                    if len(content) > MAX_TOOL_CHARS:  # keep it valid JSON for the model
                        content = json.dumps({"truncated": True, "note": "result too large: narrow the query",
                                              "preview": content[:MAX_TOOL_CHARS]})
                    self.messages.append({"role": "tool", "tool_call_id": tc.id, "content": content})
            else:  # step limit: answer from what the tools returned so far
                self.messages.append({"role": "user", "content": "Stop calling tools. Answer the original question now "
                                      "from the tool results above, in the answer format, and say what you could not verify."})
                r = self._complete(final=True)
                text = _THINK.sub("", r.choices[0].message.content or "").strip()
                del self.messages[-1]
                self.messages.append({"role": "assistant", "content": text})
        except Exception:
            del self.messages[start:]  # keep the conversation consistent for the next turn
            raise
        statuses = {t["result"].get("data_status") for t in self.trace if isinstance(t["result"], dict)} - {None}
        return {"question": question, "answer": text, "trace": list(self.trace), "citations": check_citations(text),
                "data_status": sorted(statuses), "model": self.model, "tokens": usage}


def make_copilot(history: list[tuple[str, str]] | None = None):
    """Provider by LLM_PROVIDER (featherless | gemini); default featherless when its key is set."""
    provider = os.environ.get("LLM_PROVIDER") or ("featherless" if os.environ.get("FEATHERLESS_API_KEY") else "gemini")
    if provider == "featherless":
        return OpenAICopilot(history=history)
    return Copilot(history=history)


def current_model() -> str:
    provider = os.environ.get("LLM_PROVIDER") or ("featherless" if os.environ.get("FEATHERLESS_API_KEY") else "gemini")
    from .agent import MODEL as GEMINI_MODEL
    return MODEL if provider == "featherless" else GEMINI_MODEL
