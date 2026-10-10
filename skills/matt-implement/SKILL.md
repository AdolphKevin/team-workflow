---
name: matt-implement
description: "Implement a piece of work based on a spec or set of tickets."
---

Before following this method, read the [team integration rules](../team-workflow/references/matt-integration.md). They define the single CS knowledge entry, document ownership, verification and authorization boundaries.


Implement the work described by the user in the spec or tickets.

If the user passes a ticket reference, fetch it from the issue tracker and state its title before starting. If the reference is ambiguous, ask.

Use the bundled `matt-tdd` method when test-first development fits the task, at existing or agreed public boundaries.

Run the appropriate focused checks, then the project-required wider checks for the actual risk. Record real results with team-workflow.

Once done, call the bundled skill `matt-code-review` to review the work.

Complete CS task writeback and team-workflow verification. Commit only when requested or already authorized.
