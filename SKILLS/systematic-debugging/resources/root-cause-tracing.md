# Root Cause Tracing

## Overview
Bugs often manifest deep in the call stack. Fixing where the error appears is treating a symptom.
**Core principle:** Trace backward through the call chain until you find the original trigger, then fix at the source.

## The Process

### 1. Observe the Symptom
`Error: git init failed in /packages/core`

### 2. Find Immediate Cause
What code directly causes this?
`execFileAsync('git', ['init'], { cwd: projectDir });`

### 3. Ask: What Called This?
Trace up the stack:
`WorktreeManager` -> `Session` -> `Project.create()`

### 4. Keep Tracing Up
What value was passed? `projectDir = ''` (empty string)
Where did it come from? `setupCoreTest()` returns empty tempDir.

### 5. Find Original Trigger
Root cause: Top-level variable initialization accessing empty value before `beforeEach` runs.

## Key Principle
**NEVER fix just where the error appears.** Trace back to the original trigger.
