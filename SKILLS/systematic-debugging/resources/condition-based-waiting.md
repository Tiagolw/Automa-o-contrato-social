# Condition-Based Waiting

## Overview
Flaky tests often guess at timing with arbitrary delays (`setTimeout`).
**Core principle:** Wait for the actual condition you care about.

## Core Pattern
❌ **BEFORE:** Guessing at timing
`await sleep(50);`
`expect(result).toBeDefined();`

✅ **AFTER:** Waiting for condition
`await waitFor(() => getResult() !== undefined);`

## Implementation
Use a polling loop that checks the condition every X ms until a timeout is reached. Includes a clear error message on timeout.
