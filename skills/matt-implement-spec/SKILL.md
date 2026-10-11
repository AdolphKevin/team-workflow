---
name: matt-implement-spec
description: "Implement the result of /to-spec and /to-tickets in code."
---

Before using this method, read the [CS integration rules](../team-workflow/references/matt-integration.md) for prerequisites and the shared knowledge entry.


You have been provided a spec. This spec should have tickets associated with it, describing how to implement the spec.

Use the project tracker and labels already configured. If absent, retain a local task draft.

The goal is the entire spec implemented on a single **integration branch**, with every ticket resolved the way the issue tracker closes work.

The tickets are not a list of steps. They are a **task graph** with blocking relationships between them. This means there is always a **frontier** of tickets which are ready to be grabbed.

Communication to and from subagents should be sparse. Communicate primarily through **context pointers**: to the spec, tickets, research notes, and previous commits. Don't duplicate information already available via pointers.

Use subagents and worktrees only when authorized and useful. Otherwise execute the same task graph in the current agent, keeping the per-ticket acceptance and final review. When the project forbids extra checkouts (for example shared workspace files above the repository), skip steps 4–6's per-ticket worktrees and implement the frontier serially in the current checkout. With the [stage flow](../team-workflow/references/stage-flow.md) enabled, record any subagent fan-out in its ledger and stop at its hard-pause triggers.

## Steps

1. Read the spec and tickets to understand the task graph.

2. (optional) Use an **exploration subagent** to conduct any exploration required by the tickets - relevant codebase files or external documentation. Ensure the exploration subagent can save files - it should save its markdown notes in a directory outside the repo, accessible by all future subagents. This lets **implementer subagents** focus on implementation rather than exploration.

3. Use the agreed branch strategy. Create a draft PR or closing links only when requested or already authorized, after there is a reviewable change.

4. Use **implementer subagents** to implement each ticket, each in its own worktree on its own branch. Each implementer subagent:
   - confirms its worktree is based on the integration branch before starting, and preserves existing changes when selecting a suitable checkout;
   - calls the bundled skill `matt-tdd` to build the ticket;
   - merges the integration branch tip into its own branch before reporting done

5. Once an **implementer subagent** completes, merge its work to the integration branch with a **merger subagent**.

6. If this changes the **frontier** of available tickets, kick off more **implementer subagents** to work on the new tickets. This allows for maximum concurrency.

7. Once all tickets are complete, call the bundled skill `matt-code-review` on the integration branch. Fix all issues raised by the code review in a single **implementer subagent**.

8. Finish the logical task under the shared CS integration rules. Report the branch and unresolved acceptance. Change external issue or PR status only within existing authorization.

9. Clean up only task-owned temporary worktrees after preserving their work.
