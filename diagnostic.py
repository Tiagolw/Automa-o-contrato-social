import os
import sys

def main():
    print(f"Current Working Directory: {os.getcwd()}")
    print(f"ANTIGRAVITY_AGENT: {os.environ.get('ANTIGRAVITY_AGENT')}")
    print(f"SHELL: {os.environ.get('SHELL')}")
    print(f"COMSPEC: {os.environ.get('COMSPEC')}")
    print(f"TERM_PROGRAM: {os.environ.get('TERM_PROGRAM')}")
    print(f"VSCODE_SHELL_INTEGRATION: {os.environ.get('VSCODE_SHELL_INTEGRATION')}")
    
    # Try to write to a visible file
    with open('diagnostic_output.txt', 'w') as f:
        f.write(f"CWD: {os.getcwd()}\n")
        f.write(f"ANTIGRAVITY_AGENT: {os.environ.get('ANTIGRAVITY_AGENT')}\n")
        f.write(f"ENV: {dict(os.environ)}\n")

if __name__ == "__main__":
    main()
