"""Content cleaning utilities — strip hallucinated XML tool call syntax from LLM text output."""

import re


def clean_content(text: str) -> str:
    """Remove hallucinated XML tool call syntax from LLM text output."""
    for pat in [
        r'<invoke(?:\s+[^>]*)?>.*?</invoke>',  # <invoke>, <invoke name="x">, <invoke name="x" extra="y">
        r'<tool_calls>.*?</tool_calls>',
        r'<function[^>]*>.*?</function>',  # <function=search>, <function name="x">, bare <function>
        r'\[tool_calls\].*?\[/tool_calls\]',
        r'<function_calls>.*?</function_calls>',
        r'<tool_call>.*?</tool_call>',
        r'<function_call>.*?</function_call>',
        r'<tool(?:\s+[^>]*)?>.*?</tool>',  # <tool name="x">, <tool name="x" extra="y">
        r'<action>.*?</action>',
        r'<parameter[^>]*>.*?</parameter>',  # stray parameter tags
    ]:
        text = re.sub(pat, '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)  # collapse excess blank lines
    text = text.strip()
    # If only punctuation/symbols remain after cleanup, clear it
    if text and not re.search(r'[a-zA-Z0-9\u0080-\uFFFF]', text):
        text = ""
    return text
