import subprocess
import os

def run_git_push():
    env = os.environ.copy()
    env['GIT_TERMINAL_PROMPT'] = '0'
    # Force SSH to use non-interactive mode if applicable
    env['GIT_SSH_COMMAND'] = 'ssh -o BatchMode=yes'
    
    print("--- Attempting Non-Interactive Git Push ---")
    try:
        res = subprocess.run(['git', 'push'], 
                             capture_output=True, 
                             text=True, 
                             env=env, 
                             timeout=30)
        print("STDOUT:", res.stdout)
        print("STDERR:", res.stderr)
    except subprocess.TimeoutExpired:
        print("TIMEOUT: Command still hanging even with prompts disabled.")
    except Exception as e:
        print("ERROR:", e)

if __name__ == "__main__":
    run_git_push()
