---
description: Create a Product Requirements Document from conversation
---

# Create PRD Workflow

Generate a comprehensive Product Requirements Document (PRD) based on the current conversation context.

## 1. Extract Requirements

**Goal**: Gather all necessary information for the PRD.

1.  Review the entire conversation history.
2.  Identify explicit requirements and implicit needs.
3.  Note technical constraints and preferences.
4.  Capture user goals and success criteria.

## 2. Synthesize Information

**Goal**: Organize requirements into a structured format.

1.  **Structure**:
    - **Executive Summary**: 2-3 paragraphs, value proposition, MVP goal.
    - **Mission**: Statement and core principles (Simplicity, Transparency, etc.).
    - **Target Users**: Detailed Personas (Goals, Needs, Pain Points).
    - **MVP Scope**: In-Scope (✅) vs Out-of-Scope (❌).
    - **User Stories**: "As a [user], I want to [action], so that [benefit]".
    - **Core Architecture & Patterns**: 
        - **MUST include ASCII High-Level Architecture Diagram**.
        - **MUST include ASCII Directory Structure**.
        - Key Design Patterns.
    - **Technology Stack**: Backend, frontend, dependencies.
    - **Database Schema**: 
        - **MUST include normalized schema definitions (Tables, PKs, FKs)**.
    - **Implementation Phases**: 3-4 actionable phases.

## 3. Write the PRD

**Goal**: Document the requirements in a markdown file.

1.  **File Path**: `PRD.md` (or user specified).
2.  **Format**: Use standard markdown with clear headings.
3.  **Content**: Fill in all sections from Step 2.
4.  **Confirm**:
    - Verify all sections are present.
    - Ensure MVP scope is realistic.
    - Check that implementation phases are actionable.

## 4. Output Confirmation

1.  Confirm the file path where the PRD was written.
2.  Provide a brief summary of contents.
3.  Highlight any assumptions made.
4.  Suggest next steps (e.g., review, planning).
