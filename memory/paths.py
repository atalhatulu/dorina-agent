"""Shared path validation for procedural memory writes and lookups."""
from pathlib import Path


def validated_skill_path(root: Path, name: str) -> Path:
    """Return a contained skill directory, rejecting linked write targets."""
    if (not name or not name.strip() or name == "." or ".." in name
            or any(char in name for char in ("/", "\\", "\x00"))):
        raise ValueError("Invalid skill name")
    root = root.resolve()
    path = root / name
    skill_file = path / "SKILL.md"
    if path.is_symlink() or skill_file.is_symlink():
        raise ValueError("Symlink skill targets are not allowed")
    if not path.resolve().is_relative_to(root) or not skill_file.resolve().is_relative_to(root):
        raise ValueError("Skill path must remain inside the skills directory")
    return path
