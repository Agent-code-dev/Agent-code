# Interactive tasks foundation

Agent Code includes UI-independent primitives for interactive task execution:

- `AskUserBroker` lets a worker request clarification while the GUI/TUI remains responsive. UI callbacks should enqueue the `ask_user` event onto the existing UI event queue; they must not create Tk widgets from a worker thread.
- `UserQuestion` validates prompts, choices, custom-answer policy, and skip policy.
- `TaskStateStore` atomically persists a task objective, structured plan, status, and a bounded trajectory of observable events.

Example:

```python
from agent_code.interactive import AskUserBroker, UserQuestion

broker = AskUserBroker(on_question=ui_event_queue.put)
question = UserQuestion.create(
    "Which test command should I use?",
    ["pytest", "python -m unittest"],
)
answer = broker.ask(question, timeout=300)
```

Answer the question from the UI using `broker.answer_question(question_id, choice=...)`,
`custom_text=...`, or `skip=True`. On stop, call `broker.cancel_all()` to release
workers waiting for answers.

Task persistence deliberately excludes API keys, raw secrets, and hidden model
reasoning. Trajectory entries are for observable lifecycle and tool events only.

## Integration status

These are engine primitives. The GUI and Textual TUI do not yet expose the complete
question/answer interaction or task-history screens. Do not advertise this module
as a fully wired user-facing feature until those adapters are implemented.

## User-facing Ask User integration (2.1.5)

The desktop GUI and curses TUI now expose a built-in `ask_user` function to the
model. It accepts a required `question` and optional `options` (up to 12). The
agent worker waits on `AskUserBroker`; the GUI displays a native input dialog
from its Tk event loop, while the TUI displays the question from its curses
main loop. Both accept a listed option, a custom response, or a skip when
allowed. Stopping the task cancels pending questions so the worker is released.

The question tool is available in Plan and Build modes and does not require a
separate permission confirmation. It only gathers user input; it does not
perform file, shell, network, or other state-changing operations.
