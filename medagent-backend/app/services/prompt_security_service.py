"""Prompt-injection detection for user requests and retrieved documents."""

from __future__ import annotations

import re

_INJECTION_LINE = re.compile(
    r"(ignore (all |any )?(previous|prior) instructions|system prompt|developer message|"
    r"reveal (the )?(secret|api key|prompt)|call (a )?tool|<\/?system>|"
    r"忽略.{0,8}(指令|提示)|系统提示词|泄露.{0,8}(密钥|提示词))",
    re.IGNORECASE,
)
_EXFILTRATION = re.compile(
    r"(show|reveal|print|repeat).{0,20}(system prompt|developer message|api key|secret)|"
    r"(显示|泄露|复述).{0,12}(系统提示词|开发者消息|密钥)",
    re.IGNORECASE,
)


def neutralize_untrusted_text(text: str) -> tuple[str, bool]:
    flagged = False
    lines = []
    for line in (text or "").splitlines():
        if _INJECTION_LINE.search(line):
            lines.append("[potential prompt-injection instruction removed]")
            flagged = True
        else:
            lines.append(line)
    return "\n".join(lines), flagged


def is_prompt_exfiltration_request(text: str) -> bool:
    return bool(_EXFILTRATION.search(text or ""))
