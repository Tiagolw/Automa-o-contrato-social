---
name: systematic-debugging
description: Use when encountering any bug, test failure, or unexpected behavior, before proposing fixes. Enforces a rigorous root cause analysis process.
---

# Systematic Debugging

## When to use this skill
- Any technical issue (test failures, bugs, performance problems).
- When under time pressure (prevents thrashing).
- When a "quick fix" failed.

## Workflow
- [ ] **Phase 1: Root Cause**: Read errors, reproduce, check changes, trace data flow.
- [ ] **Phase 2: Pattern Analysis**: Find working examples, compare, identify differences.
- [ ] **Phase 3: Hypothesis**: Form variable-specific hypothesis, test minimally.
- [ ] **Phase 4: Implementation**: Create failing test, fix root cause, verify.

## Instructions

### The Iron Law & Steps
**NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST.**

1.  **Read Error Messages**: Don't skip them. They often contain the answer.
2.  **Reproduce**: Can you trigger it reliably? If not, gather data.
3.  **Trace Data Flow**: Where does the bad value originate? Trace backwards. (See `resources/root-cause-tracing.md`)
4.  **Scientific Method**: "I think X is the cause because Y". Test one variable at a time.
5.  **Fix at Source**: Don't patch the symptom. Fix the origin.
6.  **Defense in Depth**: Add validation at multiple layers. (See `resources/defense-in-depth.md`)

### Red Flags (STOP if you do this)
- "Quick fix for now"
- "Just try changing X"
- "Skip the test"
- **3+ failed fixes**: STOP. Question the architecture.

## Resources
- [root-cause-tracing.md](resources/root-cause-tracing.md): How to trace bugs backward.
- [defense-in-depth.md](resources/defense-in-depth.md): Validating at every layer.
- [condition-based-waiting.md](resources/condition-based-waiting.md): Fixing flaky tests.
