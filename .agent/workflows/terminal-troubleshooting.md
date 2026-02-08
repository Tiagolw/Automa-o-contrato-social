---
description: Troubleshooting known environment issues
---

# Troubleshooting Known Issues

## Terminal Commands Not Executing

**Problem:** Terminal commands may appear to hang or not execute properly.

**Root Cause:** The `run_command` tool may have issues with command execution in certain environments.

**Workarounds:**
1. **Verify the server is running externally** - Ask the user to run commands manually in their terminal
2. **Use syntax validation instead of execution** - Use `python -m py_compile file.py` to check for syntax errors without running
3. **Check for existing processes** - Use `read_terminal` to check terminal state before sending commands
4. **Browser testing** - If browser subagent fails due to `$HOME` not set, ask user to test manually

## Before Running Any Server

1. Review code for syntax errors first (static analysis)
2. Check that all imports are valid
3. Verify file paths and configurations
4. Ask user to confirm terminal is ready

## When Things Hang

1. Don't retry repeatedly - it will loop
2. Notify user and provide manual instructions
3. Document what was attempted
