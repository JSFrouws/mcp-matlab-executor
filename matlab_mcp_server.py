"""
MCP Server for safely executing MATLAB functions
"""

import os
import sys
import asyncio
import subprocess
import tkinter as tk
from tkinter import messagebox
import logging
from typing import Dict, Optional, Set
from datetime import datetime
from pathlib import Path
from threading import Thread
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP, Context

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("matlab_executor.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("matlab-executor")

# Default MATLAB path
DEFAULT_MATLAB_PATH = os.getenv("MATLAB_PATH", "C:/Program Files/MATLAB/R2022b/bin")

# Initialize FastMCP server
mcp = FastMCP(
    "MatlabExecutor",
    dependencies=["mcp", "tkinter", "python-dotenv"]
)

# Track allowed functions for this session
allowed_functions: Dict[str, bool] = {}
permission_result = None
permission_event = asyncio.Event()

class SecurityPrompt:
    def __init__(self):
        self.result = None
        
    def show_prompt(self, function_path: str, path_to_add: str):
        """Display security prompt and return the user's decision"""
        self.result = None
        
        # Create the window in a separate thread to not block the async loop
        def create_window():
            root = tk.Tk()
            root.title("MATLAB Function Security Prompt")
            root.geometry("600x300")
            
            # Configure the window
            frame = tk.Frame(root, padx=20, pady=20)
            frame.pack(fill=tk.BOTH, expand=True)
            
            # Warning message
            msg = tk.Label(
                frame, 
                text="⚠️ Security Warning ⚠️",
                font=("Arial", 14, "bold")
            )
            msg.pack(pady=(0, 10))
            
            # Function details
            details = tk.Label(
                frame,
                text=f"Request to execute MATLAB function:\n{function_path}\n\nWith path:\n{path_to_add}",
                justify=tk.LEFT,
                wraplength=550
            )
            details.pack(pady=(0, 20))
            
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
async def execute_matlab_function(path_to_add: str, function_path: str, ctx: Context) -> str:
    """
    Execute a MATLAB function safely with user permission
    
    Args:
        path_to_add: Path to add to MATLAB path (using addpath)
        function_path: Function to execute (with parameters)
    
    Returns:
        Output from MATLAB execution
    """
    global permission_result, permission_event
    
    logger.info(f"Request to execute MATLAB function: {function_path}")
    logger.info(f"With path: {path_to_add}")
    
    # Check if this function has already been allowed for this session
    function_key = f"{path_to_add}:{function_path}"
    if function_key in allowed_functions:
        if allowed_functions[function_key]:
            logger.info(f"Function {function_key} previously allowed in this session")
            return await run_matlab(path_to_add, function_path, ctx)
    
    # Reset the event
    permission_event.clear()
    
    # Display permission prompt
    security_prompt = SecurityPrompt()
    permission_result = security_prompt.show_prompt(function_path, path_to_add)
    
    # Check the result
    if permission_result == "deny":
        logger.warning(f"User denied execution of MATLAB function: {function_path}")
        return "Function execution denied by user."
    
    if permission_result == "always_allow":
        logger.info(f"User granted permanent permission for function: {function_path}")
        allowed_functions[function_key] = True
    
    if permission_result == "allow" or permission_result == "always_allow":
        logger.info(f"User allowed execution of MATLAB function: {function_path}")
        return await run_matlab(path_to_add, function_path, ctx)
    
    # This should not happen, but just in case
    logger.error(f"Unexpected permission result: {permission_result}")
    return "Error in permission handling. Function was not executed."

async def run_matlab(path_to_add: str, function_path: str, ctx: Context) -> str:
    """Actually run the MATLAB function after permission is granted"""
    try:
        # Get MATLAB path from environment variable or use default
        matlab_path = os.getenv("MATLAB_PATH", DEFAULT_MATLAB_PATH)
        
        # Normalize paths
        matlab_exe = os.path.join(matlab_path, "matlab.exe")
        path_to_add = path_to_add.replace("\\", "/")
        
        # Construct the MATLAB command
        matlab_command = f"addpath(genpath('{path_to_add}')); {function_path}"
        
        # Log the command being executed
        logger.info(f"Executing MATLAB command: {matlab_command}")
        
        # Build the full command
        cmd = [matlab_exe, "-batch", matlab_command]
        
        # Execute the command and capture output
        ctx.info(f"Running MATLAB: {function_path}")
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
            result = f"MATLAB function executed successfully.\n\nOutput:\n{stdout_text}"
            if stderr_text:
                result += f"\n\nWarnings/Errors:\n{stderr_text}"
        else:
            result = f"MATLAB function failed with exit code {process.returncode}.\n\nOutput:\n{stdout_text}\n\nErrors:\n{stderr_text}"
        
        return result
        
    except Exception as e:
        logger.error(f"Error executing MATLAB function: {str(e)}")
        return f"Error executing MATLAB function: {str(e)}"

# Run the server if executed directly
if __name__ == "__main__":
    print("Starting MATLAB Executor MCP Server...")
    print(f"Default MATLAB path: {DEFAULT_MATLAB_PATH}")
    print("You can change this by setting the MATLAB_PATH environment variable")
    mcp.run()
