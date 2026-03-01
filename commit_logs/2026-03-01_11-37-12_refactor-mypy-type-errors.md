# Commit: refactor: resolve mypy type errors across models and state objects

## Changes Implemented
* Refactored `src/models.py` to use SQLAlchemy 2.0 `Mapped[T] = mapped_column()` syntax, resolving direct type compatibility with type checkers.
* Handled the missing search results edge-case in `src/agents/nodes/selection_node.py` with `current_item = pending_items[0] if pending_items else None`.
* Added proper typing (`dict[str, Any]`) to `params` variable in `src/config.py` to fix kwargs dict unpacking warnings.
* Added `.calories or 0.0` fallbacks inside `calculate_food_macros()` in `src/tools/food_lookup.py` to protect against newly enforced `Optional[float]` null values.
* Muted `langgraph.checkpoint.sqlite.aio` package import checks which explicitly drop stubs.

## Next Steps
* The CI and continuous development loop now enforce strict typings, we should apply these strict bounds across any future nodes that interface with the `langgraph` state loop.
* We still have one unused variable linting warning `app = await define_graph()` in `src/main.py` which wasn't part of this `mypy` pass, we can tackle that next.
