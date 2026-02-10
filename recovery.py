import subprocess
import os
import sys

def execute():
    log_file = "recovery_log.txt"
    with open(log_file, "w", encoding="utf-8") as f:
        f.write("--- Environment ---\n")
        f.write(f"PROMPT: {os.environ.get('PROMPT', 'not set')}\n")
        f.write(f"ANTIGRAVITY_AGENT: {os.environ.get('ANTIGRAVITY_AGENT', 'not set')}\n")
        
        f.write("\n--- Testing simple echo ---\n")
        try:
            res = subprocess.run("echo hello from subprocess", shell=True, capture_output=True, text=True)
            f.write(f"STDOUT: {res.stdout}\n")
            f.write(f"STDERR: {res.stderr}\n")
        except Exception as e:
            f.write(f"ERROR: {e}\n")

        f.write("\n--- Running git status with clean environment ---\n")
        env = os.environ.copy()
        env['PROMPT'] = '$G'
        try:
            res = subprocess.run(['git', 'status'], capture_output=True, text=True, env=env)
            f.write(f"STDOUT: {res.stdout}\n")
            f.write(f"STDERR: {res.stderr}\n")
        except Exception as e:
            f.write(f"ERROR: {e}\n")

        f.write("\n--- Attempting git push ---\n")
        try:
            # We don't want to hang if it asks for credentials, 
            # but git push usually fails immediately if not configured.
            res = subprocess.run(['git', 'push'], capture_output=True, text=True, env=env, timeout=30)
            f.write(f"STDOUT: {res.stdout}\n")
            f.write(f"STDERR: {res.stderr}\n")
        except subprocess.TimeoutExpired:
            f.write("PUSH TIMEOUT (maybe waiting for credentials?)\n")
        except Exception as e:
            f.write(f"ERROR: {e}\n")

if __name__ == "__main__":
    execute()
