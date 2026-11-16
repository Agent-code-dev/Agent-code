# Claude Code-compatible instruction skills

Agent Code can load instruction-only Claude Code-style skills from a `SKILL.md` file. These do not need `skill.py` and do not execute Python.

Supported locations:

- `<workspace>/.claude/skills/<skill-name>/SKILL.md`
- `~/.claude/skills/<skill-name>/SKILL.md`
- Agent Code's global skills directory, with either `SKILL.md` or `skill.md`

Example:

```markdown
---
name: code-review
 description: Review code changes for correctness, security, and tests
---

# Code review

Inspect the changed files, identify edge cases, and run relevant tests.
```

The YAML-style frontmatter may include `name`, `description`, `version`, `license`, and `compatibility`. The skill body is added to the agent's instruction context. Files are size-limited and the combined context has a fixed upper bound. Use the Skills dialog to enable or disable these instructions. Use native `skill.py` modules when a skill needs to expose executable tools.
