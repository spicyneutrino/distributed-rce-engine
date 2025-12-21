import subprocess
import os
import tempfile

def run_code_in_container(code_content: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode= 'wb', dir=os.getcwd()) as tmp:
        tmp.write(code_content)
        tmp_path = tmp.name
        
    try:
        # Podman Container
        # --rm: Delete container after run
        # --network none: NO INTERNET ACCESS (Security)
        # -v: Mount the temp file into the container at /app/script.py
        # python:3.9-slim: The image to run
        cmd = [
            "podman", "run", "--rm",
            "--network", "none",
            "--memory", "128m",  # Limit RAM to prevent crashes
            "--cpus", "0.5",     # Limit CPU
            "-v", f"{tmp_path}:/app/script.py:ro,Z",
            "docker.io/library/python:3.9-slim",
            "python", "/app/script.py"
        ]
        
        print(f"DEBUG: Executing {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10 # Kill if it runs longer than 10s
        )
        
        if result.returncode == 0:
            return result.stdout
        else:
            return f"Error (Exit Code {result.returncode}):\n{result.stderr}"
    
    except subprocess.TimeoutExpired:
        return "Error: Execution timed out."
    except Exception as e:
        return f"System Error: {str(e)}"
    finally:
        # Cleanup temp file on host
        if os.path.exists(tmp_path):
            os.remove(tmp_path)