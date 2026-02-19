---
description: Review GitHub Pull Requests and validate architectural decisions
---

# PR Review Workflow

Automated workflow for reviewing GitHub Pull Requests. The agent fetches the PR context (description, diff, comments) using `github-mcp-server`, analyzes the changes against project standards, and posts a comprehensive review calling out architectural decisions and potential issues.

## 1. Prerequisites
- **MCP Server**: `github-mcp-server` must be active.
- **Tools**:
  - `mcp_github-mcp-server_pull_request_read`: To fetch PR details, diffs, and review threads.
  - `mcp_github-mcp-server_pull_request_review_write`: To create/submit reviews.
  - `mcp_github-mcp-server_add_comment_to_pending_review`: To add **inline** comments to a pending review.

## 2. Usage

```
@[/commit_review] [PR_NUMBER] [OWNER] [REPO]
```

Example: `@[/commit_review] 15 sandrusidoltst-a11y fit_pal`

## 3. Process

### Step 1: Fetch PR Context
1.  **Read PR Details**:
    - Call `mcp_github-mcp-server_pull_request_read(method="get", ...)` matches.
    - Extract **Title**, **Description**, and **State**.
    - *Note*: The PR Description is the primary "Change Log".
2.  **Read Code Changes**:
    - Call `mcp_github-mcp-server_pull_request_read(method="get_diff", ...)`
    - Analyze the raw diff to understand the implementation.
3.  **Read Review Threads**:
    - Call `mcp_github-mcp-server_pull_request_read(method="get_review_comments", ...)`
    - Identify existing threads where the user has asked questions on specific lines of code.

### Step 2: Analyze Changes
Compare the implementation against:
1.  **Project Rules**: `.agent/rules/main_rule.md` (e.g., specific tech stack usage, file organization).
2.  **Architecture**: `PRD.md` (e.g., node responsibilities, state schema).
3.  **Code Quality**: Type safety, error handling, and test coverage.

### Step 3: Analyze User Questions
For every question found in the **PR Description** or **Inline Comments**, apply this logic:

1.  **Analyze the Intent**:
    - Does the question stem from a **lack of understanding** or **incorrect assumptions** about the architecture/workflow?
    - OR, does it identify a **real architectural or engineering flaw**?

2.  **Formulate Response**:
    - **Scenario A (Misunderstanding)**:
        - Clearly explain *what* was misunderstood.
        - Explain *why* the current code/approach is actually correct.
        - detail the *architectural decision* behind it.
    - **Scenario B (Valid Concern/Flaw)**:
        - Validate that the concern is correct.
        - Explain the specific problem (e.g., "This breaks the write-through pattern").
        - **Suggest a fix**: Provide a concrete alternative approach.

### Step 4: Post Review (Inline & Summary)

Construct a review using the **Pending Review** flow to batch comments.

1.  **Start Review**:
    - `mcp_github-mcp-server_pull_request_review_write(method="create", ...)` (Draft mode).

2.  **Reply Inline (For Code Comments)**:
    - If the user asked a question on a specific line/thread:
    - Use `mcp_github-mcp-server_add_comment_to_pending_review`.
    - Post the specific answer (Scenario A or B) directly to that thread.

3.  **Draft Summary (For PR Description/General)**:
    - Prepare the "body" of the review containing:
        - **General Q&A**: Answers to questions in the PR description.
        - **Architectural Analysis**: Review of patterns and consistency.
        - **Critical Feedback**: Any other issues found.
        - **Verdict**: Approval or Request Changes.

4.  **Submit Review**:
    - Call `mcp_github-mcp-server_pull_request_review_write(method="submit_pending", body="[Your Summary Here]", event="[APPROVE/REQUEST_CHANGES/COMMENT]")`.

## 4. Proactive Checks
Always verify:
- **Environment**: Are `uv` commands used correctly?
- **Testing**: Are unit tests included?
- **Documentation**: Is the code self-documenting?

### Step 5: Reply to Inline Comments (Hybrid Approach)

**Constraint**: The `github-mcp-server` currently lacks the `in_reply_to` parameter needed for proper threading.
**Workaround**: Use the `gh` CLI for replies.

1.  **Fetch Comment IDs**:
    - Use `mcp_github-mcp-server_pull_request_read(method="get_review_comments")` to find the `id` of the user's comment.

2.  **Formulate Reply**:
    - **Format Requirement**: Start every reply with:
      `🤖 **Sandro**: [Your actual response in Markdown]`
    - **Content**: Address the user's specific question using clear markdown (bolding, code blocks, lists).
    - **Example**:
      `🤖 **Sandro**: That is a good point! The `TypedDict` structure ensures type safety.`

3.  **Execute Reply (Terminal)**:
    - Construct a single-line `gh api` command.
    - **Critical Formatting (PowerShell)**:
      - Escape double quotes `"` as `\"`.
      - **Use backtick-n (`n) for newlines**. Do not use `\n`.
      - Use `**` for bold text.
    - **Command Template**:
      ```powershell
      gh api repos/[OWNER]/[REPO]/pulls/[PR_NUMBER]/comments -f body="🤖 **Sandro**: First line.`n`nSecond line." -F in_reply_to=[COMMENT_ID]
      ```
