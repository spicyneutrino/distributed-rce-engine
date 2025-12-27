import subprocess
import os


def run_code_in_container(code_content: bytes) -> str:
    # Path only for Seccomp
    host_path = os.getenv("HOST_PROJECT_PATH")
    seccomp_profile_path = os.path.join(host_path, "seccomp_profile.json")

    try:
        # Pass the code directly to Python via "Standard Input" (stdin).
        
        cmd = [
            "podman", "run", "--rm",
            "-i",              # Interactive (Allows reading input)
            "--network", "none",
            "--memory", "128m",
            "--cpus", "0.5",
            "--pids-limit", "64",
            "--cap-drop=ALL",
            # Mount the Seccomp profile because it's a config file, not user data
            f"--security-opt=seccomp={seccomp_profile_path}",
            
            "localhost/rce-datascience",
            "python", "-"      # The "-" tells Python to read code from stdin
        ]
        
        print(f"DEBUG: Executing {' '.join(cmd)}")
        
        # Pass the code_content directly into 'input='
        result = subprocess.run(
            cmd,
            input=code_content.decode('utf-8'), # Pipe the code string here
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            return result.stdout
        else:
            # If Seccomp blocks it, we can see it here
            return f"Error (Exit Code {result.returncode}):\n{result.stderr}"
    
    except subprocess.TimeoutExpired:
        return "Error: Execution timed out."
    except Exception as e:
        return f"System Error: {str(e)}"