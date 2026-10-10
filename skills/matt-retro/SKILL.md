---
name: matt-retro
description: "Review a coding session to improve the agent's working environment when an environment retrospective or improvement is requested. Produces suggestions, not a code review or a routine task-completion step."
---

Before using this method, read the [CS integration rules](../team-workflow/references/matt-integration.md) for prerequisites and the shared knowledge entry.

Suggest improvements to the coding agent's **environment** from the session the user identifies; default to the current session. Focus on the environment goal already in the task.

## Inspect the session

Read the available primary evidence for that session and the relevant environment files. Distinguish observed problems from hypotheses and unavailable history; a missing transcript does not prove a step was skipped.

Look for improvements supported by that evidence:

- **Navigation**: repeated searches, hidden dependencies or missing pointers that made the right information hard to find.
- **Automated checks**: mistakes a deterministic check could catch. Inspect existing commands, hooks and CI first; identify broken or unwired checks before proposing another one. Missing checks can be a finding when tied to the project's work.
- **Instructions**: conflicting, redundant or ineffective steering in agent instructions and skills. When proposing new instructions, consult the bundled `matt-writing-for-agents` method.
- **Tool economy**: expensive or repetitive calls that could be reduced without losing needed information.
- **Information access**: missing logs, documentation or permitted read access that prevented sound decisions.

## Present improvements

Rank findings by their effect on future work. For each, identify the observed problem, its evidence, the proposed environment change and how to check that the change helps. Say when no supported improvement was found.

The result is a set of recommendations. Implement changes only when they are part of the user's authorized task. This method adds no separate code-review rules or knowledge-maintenance steps.
