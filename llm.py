"""DeepSeek streaming chat client."""
from __future__ import annotations

import json
from typing import Callable, Iterable

import requests

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"

# Connection / read timeouts (seconds). Read timeout is generous because the
# model can be slow to emit the first token, but not infinite.
CONNECT_TIMEOUT = 15
READ_TIMEOUT = 90

# A persistent Session keeps the TCP+TLS connection alive between calls, so
# every question after the first skips the handshake (~100–300 ms saved).
_SESSION = requests.Session()


# Shared rule that teaches the model to pick the RIGHT kind of answer.
_CLASSIFY_RULE = (
    "First, silently classify the interviewer's question into one of:\n"
    "  (A) KNOWLEDGE / TECHNICAL — asks what something is, how it works, a "
    "definition, a comparison, or to solve/explain a technical problem "
    "(e.g. 'what is Terraform', 'explain OAuth', 'difference between a list "
    "and a tuple', 'how would you design a rate limiter'). For these: give a "
    "DIRECT, ACCURATE, concise answer to the actual question. Do NOT tell a "
    "personal story. Do NOT use STAR. You may add ONE short sentence at the "
    "end connecting it to the candidate's experience ONLY if it is genuinely "
    "relevant. Include a small fenced code snippet only if it truly helps.\n"
    "  (B) BEHAVIORAL / EXPERIENCE — asks about the candidate themselves: a "
    "past situation, a strength/weakness, motivation, 'tell me about a time', "
    "'why this role'. For these: answer in first person, confident and "
    "specific, grounded in the candidate's resume, using STAR structure "
    "(Situation, Task, Action, Result) where it fits.\n"
    "Never invent facts about the candidate. If the resume doesn't cover "
    "something, keep the behavioral answer general rather than fabricating. "
    "Answer the question that was actually asked — do not pad with resume "
    "content that wasn't asked for. No preamble, no 'great question'."
)

SYSTEM_PROMPTS = {
    "bullets_then_full": (
        "You are an interview copilot helping the candidate answer the question "
        "the interviewer just asked.\n\n"
        f"{_CLASSIFY_RULE}\n\n"
        "Then reply in this EXACT format, nothing before or after:\n\n"
        "BULLETS:\n• 3 to 5 ultra-concise bullets (max 12 words each) the "
        "candidate can glance at and rephrase while speaking.\n\n"
        "FULL ANSWER:\n2 to 4 short paragraphs the candidate could say aloud."
    ),
    "bullets": (
        "You are an interview copilot.\n\n"
        f"{_CLASSIFY_RULE}\n\n"
        "Reply with ONLY 3 to 5 ultra-concise bullets (max 12 words each) the "
        "candidate can glance at and rephrase while speaking. No headers, no "
        "closing line."
    ),
    "full": (
        "You are an interview copilot.\n\n"
        f"{_CLASSIFY_RULE}\n\n"
        "Reply with 2 to 4 short paragraphs the candidate could say aloud. "
        "No headers, no bullets."
    ),
}


def build_messages(
    question: str,
    resume: str,
    job_description: str,
    style: str,
) -> list[dict]:
    system = SYSTEM_PROMPTS.get(style, SYSTEM_PROMPTS["bullets_then_full"])
    context_parts = []
    if resume:
        context_parts.append(f"### Candidate resume\n{resume}")
    if job_description:
        context_parts.append(f"### Job description\n{job_description}")
    context = "\n\n".join(context_parts) if context_parts else "(no resume / JD provided)"

    user = (
        f"{context}\n\n"
        f"### Interviewer just asked\n{question}\n\n"
        "Answer now."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def stream_completion(
    api_key: str,
    model: str,
    messages: list[dict],
    on_delta: Callable[[str], None],
    on_done: Callable[[], None],
    on_error: Callable[[str], None],
    stop_check: Callable[[], bool] = lambda: False,
) -> None:
    """Stream a chat completion from DeepSeek."""
    if not api_key:
        on_error("Missing DeepSeek API key — open Settings to add one.")
        return
    if not model:
        on_error("No DeepSeek model set — open Settings and fill in the model id.")
        return

    url = DEEPSEEK_URL
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "temperature": 0.3,
        "max_tokens": 200,
    }

    try:
        with _SESSION.post(
            url,
            headers=headers,
            json=payload,
            stream=True,
            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
        ) as resp:
            if resp.status_code != 200:
                body = resp.text[:500]
                if resp.status_code == 404:
                    on_error(
                        f"HTTP 404 from DeepSeek — the model id '{model}' "
                        f"may not be valid. Open Settings and check the "
                        f"DeepSeek model field.\n\nServer said: {body}"
                    )
                elif resp.status_code in (401, 403):
                    on_error(
                        f"HTTP {resp.status_code} — your DeepSeek API key was "
                        f"rejected. Check the key in Settings.\n\nServer said: {body}"
                    )
                else:
                    on_error(f"DeepSeek HTTP {resp.status_code}: {body}")
                return
            for raw in resp.iter_lines(decode_unicode=True):
                if stop_check():
                    return
                if not raw:
                    continue
                if raw.startswith("data: "):
                    raw = raw[6:]
                if raw == "[DONE]":
                    break
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                try:
                    delta = obj["choices"][0]["delta"].get("content", "")
                except (KeyError, IndexError):
                    delta = ""
                if delta:
                    on_delta(delta)
        on_done()
    except requests.exceptions.ReadTimeout:
        on_error(
            f"DeepSeek accepted the request but sent no response within "
            f"{READ_TIMEOUT}s. It may be under heavy load — try again, or "
            f"check the model id in Settings."
        )
    except requests.exceptions.ConnectTimeout:
        on_error("Could not reach DeepSeek — connection timed out. Check your internet.")
    except requests.RequestException as exc:
        on_error(f"Network error: {exc}")
