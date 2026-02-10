import subprocess
import os
import sys
import time

def run_cmd(args, env=None, cwd=None):
    try:
        res = subprocess.run(args, capture_output=True, text=True, env=env, cwd=cwd, timeout=60, shell=True if isinstance(args, str) else False)
        return f"STDOUT: {res.stdout}\nSTDERR: {res.stderr}\nCODE: {res.returncode}\n"
    except Exception as e:
        return f"ERROR: {e}\n"

def probe_and_push():
    log_file = "deep_recovery_log.txt"
    with open(log_file, "w", encoding="utf-8") as f:
        f.write("=== Deep Recovery Probe ===\n")
        f.write(f"CWD: {os.getcwd()}\n")
        f.write(f"PYTHON: {sys.executable}\n")
        
        env = os.environ.copy()
        env['PROMPT'] = '$G'
        env['ANTIGRAVITY_AGENT'] = '0' # Try disabling it to see if it changes behavior
        env['GIT_TERMINAL_PROMPT'] = '0'
        env['GIT_SSH_COMMAND'] = 'ssh -o BatchMode=yes'
        
        f.write("\n--- Testing chcp 65001 ---\n")
        f.write(run_cmd("chcp 65001", env=env))
        
        f.write("\n--- Git Status ---\n")
        f.write(run_cmd(['git', 'status'], env=env))
        
        f.write("\n--- Git Remote ---\n")
        f.write(run_cmd(['git', 'remote', '-v'], env=env))
        
        f.write("\n--- Attempting Git Push (Final) ---\n")
        f.write(run_cmd(['git', 'push'], env=env))
        
        f.write("\n--- End of Probe ---\n")

if __name__ == "__main__":
    probe_and_push()
