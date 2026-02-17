---
description: Review commits and validate architectural decisions
---

# Commit Review Workflow

Interactive workflow for critical analysis of commits. User provides a commit log and specific questions/concerns, and the agent responds with architectural validation and critical feedback.

## Usage

```
@[/commit_review] @[commit_logs/2026-02-12_feat-example.md]

Questions:
1. Why did we choose pattern X instead of Y?
2. Is my assumption about Z correct?
3. Should we have handled edge case W differently?
```

## Process

### 1. Load Commit Context

1. **Read the provided commit log**:
   - Understand what files were changed (new/modified/deleted)
   - Review validation results and test coverage
   - Identify the scope and purpose of changes

2. **Examine implementation files**:
   - Read the actual code changes mentioned in the commit
   - Understand the implementation in full context
   - Check related documentation updates (PRD, plans, etc.)

### 2. Address User Questions

For each question or concern raised:

1. **Validate or Correct Assumptions**:
   - Confirm if the user's understanding is correct
   - Correct any misunderstandings with clear explanations
   - Provide context for why things work the way they do

2. **Explain Architectural Decisions**:
   - **Context**: What problem was being solved?
   - **Options Considered**: What alternatives existed?
   - **Decision Rationale**: Why was this specific approach chosen?
   - **Trade-offs**: What are the pros and cons of this choice?
   - **Future Implications**: How does this affect future development?

3. **Provide Critical Analysis**:
   - Be honest about whether the approach was optimal
   - Identify any issues, edge cases, or concerns
   - Suggest improvements if applicable
   - Explain if a different approach would have been better and why

### 3. Proactive Review

Beyond answering specific questions, also:

1. **Identify Potential Issues**:
   - Logic errors or edge cases not handled
   - Performance concerns or inefficiencies
   - Maintainability or code clarity issues
   - Security or data handling concerns

2. **Evaluate Design Patterns**:
   - Verify consistency with existing codebase patterns
   - Assess if pattern choice is appropriate
   - Check for architectural violations or coupling issues

3. **Review Test Coverage**:
   - Evaluate if tests adequately cover functionality
   - Identify missing test cases
   - Assess test quality and maintainability

## Output Format

Provide a structured response:

### Questions & Answers
- Address each user question directly
- Validate or correct assumptions
- Explain architectural reasoning

### Architectural Analysis
- Key design decisions and their rationale
- Trade-offs and alternatives considered
- Integration with existing architecture

### Critical Feedback
- Issues found (if any)
- Suggested improvements
- Follow-up considerations

### Verdict
- Overall assessment: ✅ Solid / ⚠️ Needs Improvement / ❌ Requires Changes
- Summary of key takeaways
