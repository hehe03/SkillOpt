from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PROMPT_FILE = SCRIPT_DIR / "prompt.md"
RESPONSE_FILE = SCRIPT_DIR / "response.md"


def create_prompt_file(question: str) -> None:
    PROMPT_FILE.write_text(question, encoding="utf-8")
    print(f"Created: {PROMPT_FILE}")


def call_harness_with_stdin(prompt: str, timeout: int = 120) -> str:
    nga_path = Path(r"C:\Users\h00576353\OCHOME\nga.cmd")
    prompt_file = SCRIPT_DIR / "prompt.md"
    prompt_file.write_text(prompt, encoding="utf-8")
    
    try:
        instruction = "Read the attached file and answer the question directly."
        proc = subprocess.run(
            [str(nga_path), "run", instruction, "--file", str(prompt_file)],
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
            encoding="utf-8",
            errors="replace",
            cwd=str(SCRIPT_DIR),
        )
        if proc.returncode != 0:
            print(f"STDERR: {proc.stderr}")
            return proc.stdout.strip() or proc.stderr.strip()
        return proc.stdout.strip()
    except subprocess.TimeoutExpired:
        return "TIMEOUT: harness call exceeded timeout"
    except FileNotFoundError:
        return "ERROR: nga CLI not found in PATH"
    except Exception as exc:
        return f"ERROR: {type(exc).__name__}: {exc}"


def write_response(response: str) -> None:
    RESPONSE_FILE.write_text(response, encoding="utf-8")
    print(f"Written: {RESPONSE_FILE}")


def main() -> None:
    question = "请简要说明什么是欠料归因分析，以及常见的归因分支有哪些？"
    
    create_prompt_file(question)
    
    prompt_content = PROMPT_FILE.read_text(encoding="utf-8")
    print(f"Prompt content:\n{prompt_content}\n")
    
    print("Calling harness with stdin...")
    response = call_harness_with_stdin(prompt_content, timeout=120)
    
    print(f"Response:\n{response}\n")
    write_response(response)
    
    if RESPONSE_FILE.exists():
        print("Test completed successfully.")
        print(f"Response file: {RESPONSE_FILE}")
    else:
        print("Test failed: response file not created.")


if __name__ == "__main__":
    main()