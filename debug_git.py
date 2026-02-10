import subprocess
import os

def run_git():
    print("--- Running git status ---")
    try:
        res = subprocess.run(['git', 'status'], capture_output=True, text=True, encoding='utf-8')
        print("STDOUT:", res.stdout)
        print("STDERR:", res.stderr)
    except Exception as e:
        print("ERROR:", e)

    print("\n--- Current Directory ---")
    print(os.listdir('.'))

if __name__ == "__main__":
    run_git()
