"""Stage B: structured entity/relation extraction via an OpenAI-compatible
chat endpoint.

Deliberately backend-agnostic: Ollama (local test, e.g. on a Mac with no
CUDA) and vLLM's `--serve` mode (HPC, GPU) both expose the same OpenAI
chat-completions API, so the same client and prompts work against either --
only --base-url and --model change between environments.
"""

import json
import logging
from dataclasses import dataclass

from openai import OpenAI

from src.ingestion.retry import with_retry

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 60.0

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


@dataclass
class ExtractedEntity:
    name: str
    type: str


def build_user_prompt(title: str, abstract: str, candidates: list[str]) -> str:
    hint = (
        f"\n\nCandidate phrases from the text (not all are relevant; you are not "
        f"limited to these): {', '.join(candidates)}"
        if candidates
        else ""
    )
    return f"Title: {title}\n\nAbstract: {abstract}{hint}"


class ExtractionClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "not-needed",
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)
        self.model = model

    def extract(
        self, title: str, abstract: str, candidates: list[str]
    ) -> list[ExtractedEntity]:
        """Call the LLM and return parsed entities, or [] if the response
        wasn't valid JSON (logged, not raised -- one bad paper shouldn't
        kill a multi-thousand-paper batch job)."""

        def _call():
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
            )

        try:
            response = with_retry(_call, retries=3, base_delay=2.0)
        except Exception as error:
            logger.warning("LLM call failed after retries: %s", error)
            return []

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
