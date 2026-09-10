from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.models.document import Document

# The v1 "configurable checks": a plain list of functions, each easy to read,
# add to, or remove. A runtime-configurable rules engine (checks defined in a
# database/YAML file instead of code) is a deliberate later upgrade — see
# ROADMAP.md.
ALLOWED_EXTENSIONS = {".pdf", ".txt"}


@dataclass
class CheckResult:
    passed: bool
    message: str


Check = Callable[[Document], CheckResult]


def check_extension_allowed(document: Document) -> CheckResult:
    extension = Path(document.filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        return CheckResult(
            passed=False,
            message=f"File extension '{extension}' is not allowed (allowed: {allowed})",
        )
    return CheckResult(passed=True, message="File extension allowed")


def check_not_empty(document: Document) -> CheckResult:
    if document.file_size <= 0:
        return CheckResult(passed=False, message="File is empty")
    return CheckResult(passed=True, message="File is not empty")


CHECKS: list[Check] = [check_extension_allowed, check_not_empty]
