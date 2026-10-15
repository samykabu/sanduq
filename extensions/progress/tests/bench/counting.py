"""Token counting with tiktoken. Exact for the named encodings only."""
ENCODINGS = ("o200k_base", "cl100k_base")
DECLARED = "o200k_base"


def load():
    """Return {encoding name: tiktoken.Encoding}. Raises ImportError when tiktoken is missing."""
    import tiktoken
    return {name: tiktoken.get_encoding(name) for name in ENCODINGS}


def tiktoken_version():
    import tiktoken
    return getattr(tiktoken, "__version__", "unknown")


def count(encoding, text):
    return len(encoding.encode(text, disallowed_special=()))


def claude_estimate(texts, model="claude-sonnet-5-5"):
    """Optional ESTIMATED Claude count through the Anthropic count_tokens endpoint.

    Returns None unless ANTHROPIC_API_KEY and the anthropic SDK are both present. Never raises. There is no exact
    local Claude tokenizer, so this is an estimate that needs the network and is not used by any test.
    """
    import os
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
        client = anthropic.Anthropic()
        total = 0
        for text in texts:
            total += client.messages.count_tokens(model=model, messages=[{"role": "user", "content": text or " "}]).input_tokens
        return total
    except Exception:  # noqa: BLE001 - optional diagnostic, never fatal
        return None
