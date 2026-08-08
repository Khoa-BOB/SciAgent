"""Stage B: structured entity/relation extraction via an OpenAI-compatible
chat endpoint.

Deliberately backend-agnostic: Ollama (local test, e.g. on a Mac with no
CUDA) and vLLM's `--serve` mode (HPC, GPU) both expose the same OpenAI
chat-completions API, so the same client and prompts work against either --
only --base-url and --model change between environments.
"""

import json
import logging
import os
import threading
from dataclasses import dataclass

from dotenv import load_dotenv
from openai import OpenAI

from src.ingestion.retry import with_retry

load_dotenv()

logger = logging.getLogger(__name__)


def resolve_api_key(explicit: str | None, base_url: str) -> str:
    """Resolve an API key for base_url, preferring .env over a CLI flag --
    a key passed as --api-key is visible in `ps`/process listings to any
    local user, since the shell expands it into the process's argv before
    exec. Ollama/vLLM backends don't check keys at all, so a placeholder is
    fine there; only a real OpenAI endpoint needs one.
    """
    if explicit:
        return explicit
    if "openai.com" in base_url:
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise SystemExit(
                "No OpenAI API key found. Add it to sciagent-KG/.env as:\n"
                "  OPENAI_API_KEY=sk-...\n"
                "(avoid --api-key on the command line -- it leaks into `ps`/process listings)"
            )
        return key
    return "not-needed"  # Ollama/vLLM don't validate keys

DEFAULT_TIMEOUT = 60.0
# Structured entity extraction never needs more than a few hundred tokens of
# JSON. Capping completion length means a "thinking"/reasoning model that
# slips through model selection (e.g. Qwen3-style hybrid reasoning) fails
# fast on a truncated response instead of silently burning the whole
# request timeout on hidden chain-of-thought -- see enable_thinking below
# for the primary defense, this is the backstop.
MAX_COMPLETION_TOKENS = 512

EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The entity exactly as named in the text.",
                    },
                    "type": {
                        "type": "string",
                        "enum": ["method", "dataset", "topic"],
                    },
                },
                "required": ["name", "type"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["entities"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "You extract structured information from scientific paper abstracts. "
    "Given a title and abstract, identify:\n"
    "- method: named algorithms, models, or techniques the paper uses or proposes\n"
    "- dataset: named datasets or benchmarks the paper uses or introduces\n"
    "- topic: the specific research topic(s) the paper studies\n"
    "Only extract entities explicitly named in the text -- do not infer or "
    "generalize. If none are present for a type, omit them. "
    "Respond with JSON matching the given schema, nothing else."
)

# Batching multiple papers into one request cuts total request count roughly
# batch_size-fold -- the fix for providers whose limit is requests/day rather
# than tokens/day (confirmed: OpenAI capped this pipeline at 10k gpt-4o-mini
# requests/day, not on tokens).
MAX_BATCH_COMPLETION_TOKENS = 4096

BATCH_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "papers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {
                        "type": "integer",
                        "description": "0-based position of this paper in the input list.",
                    },
                    "entities": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {
                                    "type": "string",
                                    "description": "The entity exactly as named in the text.",
                                },
                                "type": {
                                    "type": "string",
                                    "enum": ["method", "dataset", "topic"],
                                },
                            },
                            "required": ["name", "type"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["index", "entities"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["papers"],
    "additionalProperties": False,
}

BATCH_SYSTEM_PROMPT = (
    "You extract structured information from scientific paper abstracts. "
    "You will be given multiple papers, each labeled with its 0-based index. "
    "For EACH paper independently, identify:\n"
    "- method: named algorithms, models, or techniques the paper uses or proposes\n"
    "- dataset: named datasets or benchmarks the paper uses or introduces\n"
    "- topic: the specific research topic(s) the paper studies\n"
    "Only extract entities explicitly named in that paper's own text -- do not "
    "infer, generalize, or mix entities between papers. If a paper has none "
    "for a type, omit them. Return exactly one entry per paper, in the same "
    "order, tagged with its index. Respond with JSON matching the given "
    "schema, nothing else."
)


@dataclass
class ExtractedEntity:
    name: str
    type: str


@dataclass
class UsageTotals:
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


def build_user_prompt(title: str, abstract: str, candidates: list[str]) -> str:
    hint = (
        f"\n\nCandidate phrases from the text (not all are relevant; you are not "
        f"limited to these): {', '.join(candidates)}"
        if candidates
        else ""
    )
    return f"Title: {title}\n\nAbstract: {abstract}{hint}"


def build_batch_user_prompt(papers: list[tuple[str, str, list[str]]]) -> str:
    """papers: (title, abstract, candidates) tuples, in index order."""
    sections = []
    for index, (title, abstract, candidates) in enumerate(papers):
        hint = (
            f"\nCandidate phrases from the text (not all are relevant; you are not "
            f"limited to these): {', '.join(candidates)}"
            if candidates
            else ""
        )
        sections.append(f"=== Paper {index} ===\nTitle: {title}\n\nAbstract: {abstract}{hint}")
    return "\n\n".join(sections)


class ExtractionClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "not-needed",
        timeout: float = DEFAULT_TIMEOUT,
        thinking_hint: bool = True,
    ) -> None:
        self.client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)
        self.model = model
        # Only meaningful for Ollama/vLLM serving Qwen3-style hybrid-reasoning
        # models -- OpenAI's hosted API (gpt-4o-mini, etc.) doesn't recognize
        # chat_template_kwargs and isn't a thinking model in the first place.
        # Set False for OpenAI/other hosted providers.
        self.thinking_hint = thinking_hint
        self._usage = UsageTotals()
        self._usage_lock = threading.Lock()  # extract() runs concurrently under a ThreadPoolExecutor

    @property
    def usage(self) -> UsageTotals:
        """Snapshot of cumulative token usage across every extract() call so far."""
        with self._usage_lock:
            return UsageTotals(self._usage.requests, self._usage.input_tokens, self._usage.output_tokens)

    def extract(
        self, title: str, abstract: str, candidates: list[str]
    ) -> list[ExtractedEntity]:
        """Call the LLM and return parsed entities, or [] if the response
        wasn't valid JSON (logged, not raised -- one bad paper shouldn't
        kill a multi-thousand-paper batch job)."""

        def _call():
            kwargs = {}
            if self.thinking_hint:
                # Best-effort attempt to disable Qwen3-style hybrid "thinking"
                # mode. vLLM documents honoring this; Ollama does NOT reliably
                # (verified locally: qwen3.5:0.8b still burned its full
                # completion budget on a hidden `reasoning` field and returned
                # empty `content`, just faster thanks to max_tokens above).
                # This is a backstop, not a fix -- the real mitigation is not
                # picking a thinking/reasoning model for extraction in the
                # first place (see DEFAULT_MODEL in extract.py).
                kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}

            return self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": build_user_prompt(title, abstract, candidates)},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "extraction",
                        "schema": EXTRACTION_SCHEMA,
                        "strict": True,
                    },
                },
                temperature=0,
                max_tokens=MAX_COMPLETION_TOKENS,
                **kwargs,
            )

        try:
            response = with_retry(_call, retries=3, base_delay=2.0)
        except Exception as error:
            logger.warning("LLM call failed after retries: %s", error)
            return []

        # Record usage even if the response body fails to parse below --
        # the tokens were spent regardless of what came back.
        if response.usage is not None:
            with self._usage_lock:
                self._usage.requests += 1
                self._usage.input_tokens += response.usage.prompt_tokens
                self._usage.output_tokens += response.usage.completion_tokens

        content = response.choices[0].message.content
        try:
            payload = json.loads(content)
            return [
                ExtractedEntity(name=e["name"], type=e["type"])
                for e in payload.get("entities", [])
                if e.get("name") and e.get("type") in ("method", "dataset", "topic")
            ]
        except (json.JSONDecodeError, TypeError, KeyError) as error:
            logger.warning("Could not parse LLM response as valid extraction JSON: %s", error)
            return []

    def extract_batch(
        self, papers: list[tuple[str, str, list[str]]]
    ) -> list[list[ExtractedEntity]]:
        """Extract entities for multiple papers in a single request.

        Returns one entity list per paper, in input order. On total failure
        (retries exhausted or unparseable response), every paper in the
        batch gets [] -- same failure semantics as extract(), just
        batch-scoped instead of per-paper.
        """
        if not papers:
            return []

        def _call():
            kwargs = {}
            if self.thinking_hint:
                kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}

            return self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": BATCH_SYSTEM_PROMPT},
                    {"role": "user", "content": build_batch_user_prompt(papers)},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "batch_extraction",
                        "schema": BATCH_EXTRACTION_SCHEMA,
                        "strict": True,
                    },
                },
                temperature=0,
                max_tokens=min(MAX_COMPLETION_TOKENS * len(papers), MAX_BATCH_COMPLETION_TOKENS),
                **kwargs,
            )

        try:
            response = with_retry(_call, retries=3, base_delay=2.0)
        except Exception as error:
            logger.warning("Batch LLM call failed after retries (%d papers): %s", len(papers), error)
            return [[] for _ in papers]

        if response.usage is not None:
            with self._usage_lock:
                self._usage.requests += 1
                self._usage.input_tokens += response.usage.prompt_tokens
                self._usage.output_tokens += response.usage.completion_tokens

        content = response.choices[0].message.content
        try:
            payload = json.loads(content)
            by_index: dict[int, list[ExtractedEntity]] = {}
            for entry in payload.get("papers", []):
                index = entry.get("index")
                entities = [
                    ExtractedEntity(name=e["name"], type=e["type"])
                    for e in entry.get("entities", [])
                    if e.get("name") and e.get("type") in ("method", "dataset", "topic")
                ]
                if isinstance(index, int) and 0 <= index < len(papers):
                    by_index[index] = entities
            return [by_index.get(i, []) for i in range(len(papers))]
        except (json.JSONDecodeError, TypeError, KeyError) as error:
            logger.warning(
                "Could not parse batch extraction JSON (%d papers): %s", len(papers), error
            )
            return [[] for _ in papers]
