"""
MCP Server for safely executing MATLAB code.
"""

import os
import sys
import asyncio
import subprocess
try:
    import tkinter as tk
except ImportError:
    print("Warning: tkinter not available. Using fallback prompt mechanism.")
    tk = None
from threading import Thread
import logging
from typing import Dict
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP, Context

__version__ = "0.1.0"

# Load environment variables from .env file if present
load_dotenv(override=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("matlab-executor")

# Default MATLAB path
DEFAULT_MATLAB_PATH = os.getenv("MATLAB_PATH", "C:/Program Files/MATLAB/R2022b/bin")

# Initialize FastMCP server
mcp = FastMCP("MatlabExecutor")

# Track allowed functions for this session
allowed_functions: Dict[str, bool] = {}

class SecurityPrompt:
    def __init__(self):
        self.result = None
        
    def show_prompt(self, matlab_code: str, path_to_add: str):
        """Display security prompt and return the user's decision"""
        self.result = None
        
        # Create the window in a separate thread to not block the async loop
        def create_window():
            root = tk.Tk()
            root.title("MATLAB Security Prompt")
            root.geometry("600x400")
            
            # Configure the window
            frame = tk.Frame(root, padx=20, pady=20)
            frame.pack(fill=tk.BOTH, expand=True)
            
            # Warning message
            msg = tk.Label(
                frame, 
                text="⚠️ MATLAB Execution Security Warning ⚠️",
                font=("Arial", 14, "bold")
            )
            msg.pack(pady=(0, 10))
            
            # Function details
            if path_to_add:
                path_info = f"With path:\n{path_to_add}\n\n"
            else:
                path_info = ""
                
            details_text = f"Request to execute MATLAB code:\n\n{matlab_code}\n\n{path_info}"
            
            # Create a frame with scrollbar for the details
            details_frame = tk.Frame(frame)
            details_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 20))
            
            scrollbar = tk.Scrollbar(details_frame)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
            details = tk.Text(
                details_frame,
                wrap=tk.WORD,
                height=10,
                yscrollcommand=scrollbar.set
            )
            details.insert(tk.END, details_text)
            details.config(state=tk.DISABLED)
            details.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            
            scrollbar.config(command=details.yview)
            
            # Buttons frame
            btn_frame = tk.Frame(frame)
            btn_frame.pack(pady=10)
            
            # Decision buttons
            def on_allow():
                self.result = "allow"
                root.destroy()
                
            def on_always_allow():
                self.result = "always_allow"
                root.destroy()
                
            def on_deny():
                self.result = "deny"
                root.destroy()
            
            allow_btn = tk.Button(
                btn_frame, 
                text="Allow Once", 
                command=on_allow,
                padx=10,
                pady=5
            )
            allow_btn.pack(side=tk.LEFT, padx=10)
            
            always_btn = tk.Button(
                btn_frame, 
                text="Always Allow", 
                command=on_always_allow,
                padx=10,
                pady=5
            )
            always_btn.pack(side=tk.LEFT, padx=10)
            
            deny_btn = tk.Button(
                btn_frame, 
                text="Deny", 
                command=on_deny,
                padx=10,
                pady=5,
                bg="#ffcccc"
            )
            deny_btn.pack(side=tk.LEFT, padx=10)
            
            # Set the window to stay on top
            root.attributes("-topmost", True)
            
            # Start the main loop
            root.mainloop()
        
        # Run the window in a separate thread
        window_thread = Thread(target=create_window)
        window_thread.daemon = True
        window_thread.start()
        window_thread.join()
        
        return self.result

@mcp.tool()
async def execute_matlab_function(path_to_add: str, matlab_code: str, ctx: Context) -> str:
    """
    Execute MATLAB code safely with user permission
    
    Args:
        path_to_add: Path to add to MATLAB path (using addpath)
        matlab_code: MATLAB function call, script, or commands to execute
    
    Returns:
        Output from MATLAB execution
    """
    logger.info(f"Request to execute MATLAB code: {matlab_code}")
    
    if path_to_add:
        logger.info(f"With path: {path_to_add}")
    
    # Check if this function has already been allowed for this session
    function_key = f"{path_to_add}:{matlab_code}"
    if function_key in allowed_functions:
        if allowed_functions[function_key]:
            logger.info(f"MATLAB code previously allowed in this session")
            return await run_matlab(path_to_add, matlab_code, ctx)
    
    # Display permission prompt
    security_prompt = SecurityPrompt()
    permission_result = security_prompt.show_prompt(matlab_code, path_to_add)
    
    # Respond to the client with what was pressed
    ctx.info(f"User response: {permission_result}")
    
    # Check the result
    if permission_result == "deny":
        logger.warning(f"User denied execution of MATLAB code: {matlab_code}")
        return "MATLAB execution denied by user."
    
    if permission_result == "always_allow":
        logger.info(f"User granted permanent permission for code: {matlab_code}")
        allowed_functions[function_key] = True
    
    if permission_result == "allow" or permission_result == "always_allow":
        logger.info(f"User allowed execution of MATLAB code: {matlab_code}")
        return await run_matlab(path_to_add, matlab_code, ctx)
    
    # This should not happen, but just in case
    logger.error(f"Unexpected permission result: {permission_result}")
    return "Error in permission handling. MATLAB code was not executed."

async def run_matlab(path_to_add: str, matlab_code: str, ctx: Context) -> str:
    """Actually run the MATLAB code after permission is granted"""
    try:
        # Get MATLAB path from environment variable or use default
        matlab_path = os.getenv("MATLAB_PATH", DEFAULT_MATLAB_PATH)
        
        # Normalize paths
        matlab_exe = os.path.join(matlab_path, "matlab.exe")
        
        # Prepare the MATLAB command
        if path_to_add:
            path_to_add = path_to_add.replace("\\", "/")
            full_matlab_code = f"addpath(genpath('{path_to_add}')); {matlab_code}"
        else:
            full_matlab_code = matlab_code
        
        # Log the command being executed
        logger.info(f"Executing MATLAB command: {full_matlab_code}")
        
        # Build the full command
        cmd = [matlab_exe, "-batch", full_matlab_code]
        
        # Execute the command and capture output
        ctx.info(f"Running MATLAB code...")
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Get output
        stdout, stderr = await process.communicate()
        
        # Decode output
        stdout_text = stdout.decode('utf-8', errors='replace')
        stderr_text = stderr.decode('utf-8', errors='replace')
        
        # Create the result message
        if process.returncode == 0:
            result = f"MATLAB execution successful.\n\nOutput:\n{stdout_text}"
            if stderr_text:
                result += f"\n\nWarnings/Errors:\n{stderr_text}"
        else:
            result = f"MATLAB execution failed with exit code {process.returncode}.\n\nOutput:\n{stdout_text}\n\nErrors:\n{stderr_text}"
        
        return result
        
    except Exception as e:
        logger.error(f"Error executing MATLAB code: {str(e)}")
        return f"Error executing MATLAB code: {str(e)}"

def main():
    """Entry point for the application"""
    print("Starting MATLAB Executor MCP Server...")
    print(f"Default MATLAB path: {DEFAULT_MATLAB_PATH}")
    print("You can change this by setting the MATLAB_PATH environment variable")
    mcp.run()

if __name__ == "__main__":
    main()
