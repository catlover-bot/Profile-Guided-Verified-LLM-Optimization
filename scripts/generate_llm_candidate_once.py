from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def strip_markdown_fences(text: str) -> str:
    text = text.strip()
    m = re.search(r"```(?:c|C)?\s*(.*?)```", text, flags=re.DOTALL)
    if m:
        return m.group(1).strip() + "\n"
    return text + ("\n" if not text.endswith("\n") else "")


def generate_openai(prompt: str, model: str, max_tokens: int, temperature: float) -> tuple[str, dict]:
    from openai import OpenAI

    client = OpenAI()
    t0 = time.time()
    resp = client.responses.create(
        model=model,
        input=prompt,
        max_output_tokens=max_tokens,
        temperature=temperature,
    )
    latency = time.time() - t0
    text = resp.output_text
    meta = {
        "provider": "openai",
        "model": model,
        "latency_sec": latency,
        "response_id": getattr(resp, "id", None),
    }
    usage = getattr(resp, "usage", None)
    if usage is not None:
        meta["usage"] = usage.model_dump() if hasattr(usage, "model_dump") else str(usage)
    return text, meta


def generate_anthropic(prompt: str, model: str, max_tokens: int, temperature: float) -> tuple[str, dict]:
    import anthropic

    client = anthropic.Anthropic()
    t0 = time.time()
    msg = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}],
    )
    latency = time.time() - t0
    text = "".join(
        block.text for block in msg.content
        if getattr(block, "type", None) == "text"
    )
    meta = {
        "provider": "anthropic",
        "model": model,
        "latency_sec": latency,
        "response_id": getattr(msg, "id", None),
        "stop_reason": getattr(msg, "stop_reason", None),
    }
    usage = getattr(msg, "usage", None)
    if usage is not None:
        meta["usage"] = usage.model_dump() if hasattr(usage, "model_dump") else str(usage)
    return text, meta


def generate_gemini(prompt: str, model: str, max_tokens: int, temperature: float) -> tuple[str, dict]:
    from google import genai
    from google.genai import types

    client = genai.Client()
    t0 = time.time()
    resp = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        ),
    )
    latency = time.time() - t0
    text = resp.text or ""
    meta = {
        "provider": "gemini",
        "model": model,
        "latency_sec": latency,
    }
    usage = getattr(resp, "usage_metadata", None)
    if usage is not None:
        meta["usage"] = usage.model_dump() if hasattr(usage, "model_dump") else str(usage)
    return text, meta


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=["openai", "anthropic", "gemini"], required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--max-tokens", type=int, default=4096)
    ap.add_argument("--temperature", type=float, default=0.2)
    args = ap.parse_args()

    prompt_path = Path(args.prompt)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    prompt = prompt_path.read_text(encoding="utf-8")

    if args.provider == "openai":
        raw, meta = generate_openai(prompt, args.model, args.max_tokens, args.temperature)
    elif args.provider == "anthropic":
        raw, meta = generate_anthropic(prompt, args.model, args.max_tokens, args.temperature)
    else:
        raw, meta = generate_gemini(prompt, args.model, args.max_tokens, args.temperature)

    code = strip_markdown_fences(raw)

    raw_path = out_dir / "raw_response.txt"
    cand_path = out_dir / "candidate.c"
    meta_path = out_dir / "metadata.json"

    raw_path.write_text(raw, encoding="utf-8")
    cand_path.write_text(code, encoding="utf-8")

    meta.update({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "prompt_path": str(prompt_path),
        "candidate_path": str(cand_path),
        "raw_response_path": str(raw_path),
        "prompt_sha256": sha256_text(prompt),
        "raw_response_sha256": sha256_text(raw),
        "candidate_sha256": sha256_text(code),
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
    })
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    print("provider:", args.provider)
    print("model:", args.model)
    print("candidate:", cand_path)
    print("metadata:", meta_path)
    print("candidate_chars:", len(code))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
