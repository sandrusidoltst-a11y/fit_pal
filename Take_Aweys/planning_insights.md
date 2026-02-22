# Planning Insights: FitPal PRD Evolution

## Executive Summary
This document analyzes the gap between our initial expectations for the FitPal project (as defined in the original [PRD.md](file:///c:/Users/User/Desktop/fit_pal/PRD.md)) and the actual implementation journey documented across 22 architectural decision records (`commit_logs/`). The goal is to identify what was missing in the initial planning phase so we can create more accurate, robust PRDs for future projects, particularly those involving LLM Agents and LangGraph.

---

## 1. What Was Missing in Initial Planning?

Comparing the first draft of the PRD against the current state reveals several critical blind spots:

### A. Underestimating State Granularity (The "TypedDict" Problem)
**Initial Plan**: The PRD assumed LangGraph state could just be generic lists of dictionaries (`List[dict]`) passed between nodes.
**Reality**: As the agent grew, unstructured state caused constant validation errors. We had to halt feature work to implement strict `TypedDict` schemas and Pydantic validation (see [2026-02-13_12-59-00_refactor-state-schema-multi-item-loop.md](file:///c:/Users/User/Desktop/fit_pal/commit_logs/2026-02-13_12-59-00_refactor-state-schema-multi-item-loop.md)). 
**What we missed**: We planned the *flow* (nodes) but not the *contract* (exact data structures) between them.

### B. The Ambiguity Escalation (Agent Selection)
**Initial Plan**: Input -> Search DB -> Calculate. 
**Reality**: What happens if the user searches for "Chicken" and the database returns 50 variations (raw, breast, thigh, fried)? The initial PRD had no contingency for this. We had to create a dedicated **Agent Selection Node** ([2026-02-12_13-19-36_feat-agent-selection-node.md](file:///c:/Users/User/Desktop/fit_pal/commit_logs/2026-02-12_13-19-36_feat-agent-selection-node.md)) just to have the LLM intelligently filter search results.
**What we missed**: Assuming deterministic logic ("search food") would yield a single, perfect result in a non-deterministic (natural language) environment.

### C. The Multi-Item Reality (Looping)
**Initial Plan**: The PRD mapped a linear flow assuming one food item per message ("I ate an apple").
**Reality**: Users say "I had 200g of chicken, rice, and an apple." The linear graph couldn't handle arrays of items. We had to redesign the entire graph architecture to support **conditional loop-back edges** to process items sequentially.
**What we missed**: Failing to account for edge cases in human conversational patterns during the MVP design phase.

### D. Separation of Internal vs. External State (LangSmith Integration)
**Initial Plan**: One unified `AgentState`.
**Reality**: LangSmith Studio expects a simple Chat UI (`messages`), but our `AgentState` was bloated with internal tracking variables (`pending_items`, `log_reports`). We had to implement the **Multiple Schemas** pattern ([2026-02-21_00-36-09_refactor_studio_schemas.md](file:///c:/Users/User/Desktop/fit_pal/commit_logs/2026-02-21_00-36-09_refactor_studio_schemas.md)).
**What we missed**: Not considering the tooling requirements (LangSmith) mapping to our data models.

---

## 2. General Lessons for Software Projects

1. **State as a Contract**: Never treat application state as an afterthought. Map out the exact data structures (schemas, types) during the PRD phase. Loose data typing in Python often leads to compounding tech debt during scaling.
2. **Design for the "Unhappy" Path Early**: PRDs frequently outline the "happy path" (User does X -> System does Y). We must dedicate equal planning time to edge cases (e.g., "What if the DB returns too many results?", "What if the DB returns zero results?").
3. **Tool/Platform Limitations vs. Business Logic**: Your architecture shouldn't just serve your business logic; it must also serve your observability tools. (e.g., refactoring schemas just so LangSmith Studio would render correctly).

---

## 3. Specific Lessons for LLM/LangGraph Projects

1. **Deterministic vs. Probabilistic boundaries**: 
   - *Lesson*: Clearly define where the LLM stops and strict code begins. In FitPal, we learned to use Pydantic `with_structured_output()` to force the LLM into returning strict JSON that our code could then deterministically process, rather than relying on the LLM to write directly to the DB.
2. **Graphs are not Pipelines; Plan for Loops**:
   - *Lesson*: LangGraph is powerful because it supports cycles. When planning a LangGraph PRD, do not draw it as a straight line (A -> B -> C). Map out the loops (A -> B -> C -> back to B) from day one. (e.g., processing multiple food items).
3. **The "Multiple Schemas" Pattern is Mandatory**:
   - *Lesson*: For any LangGraph project that will be evaluated in LangSmith or exposed via API, always design separate `InputState` (what the user sends), `OutputState` (what the user gets), and `AgentState` (the messy internal scratchpad the nodes share). 
4. **Configuration Centralization over Node Hardcoding**:
   - *Lesson*: Never bind a specific model (e.g., `gpt-4o`) directly inside a node function. As seen in the recent LLM configuration refactor, agent projects need a centralized `config.py` factory so models, temperatures, and base paths can be hot-swapped globally without altering graph logic.
