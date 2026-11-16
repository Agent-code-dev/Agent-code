# Agent Code Project Blueprints

Agent Code can keep a durable, structured description of a project's intent in
`<workspace>/.agent-code/blueprint.json`. The file is project-local and is not a
replacement for source code, tests, or the user's latest instruction.

Supported schema version: `1`.

```json
{
  "schema_version": 1,
  "title": "Project name",
  "goal": "What the finished project must accomplish",
  "requirements": ["Functional and non-functional requirements"],
  "architecture": ["Components and their responsibilities"],
  "constraints": ["Compatibility, licensing, resource, and safety constraints"],
  "milestones": ["Ordered implementation milestones"],
  "acceptance_criteria": ["Observable tests for completion"]
}
```

The blueprint store adds `updated_at`, writes atomically, validates the schema
version, and exposes the active blueprint to the agent's task context. Max Mode
is encouraged to create or revise this file for substantial projects, but must
not silently override the user's latest request. Review blueprint changes like
any other project-file change.
