import subprocess
import os
import sys

def execute():
    log_file = r"C:\Users\tiago\recovery_log.txt"
    with open(log_file, "w", encoding="utf-8") as f:
        f.write("--- Simple Recovery Test ---\n")
        f.write(f"Current Dir: {os.getcwd()}\n")
        f.write(f"Python Exec: {sys.executable}\n")
        
        try:
            # Run git status using absolute path if possible, or just git
            res = subprocess.run(['git', 'status'], capture_output=True, text=True, cwd=os.getcwd())
            f.write("\n--- Git Status ---\n")
            f.write(res.stdout)
            f.write(res.stderr)
        except Exception as e:
            f.write(f"\nERROR running git: {e}\n")

if __name__ == "__main__":
    execute()
