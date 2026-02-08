# Defense-in-Depth Validation

## Overview
Single validation can be bypassed.
**Core principle:** Validate at EVERY layer data passes through. Make the bug structurally impossible.

## The Four Layers

### Layer 1: Entry Point
Reject obviously invalid input at API boundary.
`if (!workingDirectory) throw Error(...)`

### Layer 2: Business Logic
Ensure data makes sense for this operation.
`if (!projectDir) throw Error(...)`

### Layer 3: Environment Guards
Prevent dangerous operations in specific contexts (e.g., test vs prod).
`if (TEST_ENV && !isTmpDir(dir)) throw Error(...)`

### Layer 4: Debug Instrumentation
Capture context for forensics when things go wrong.
`logger.debug('Context', { dir, vars })`

## Strategy
1. Trace data flow.
2. Map all checkpoints.
3. Add validation at each layer.
