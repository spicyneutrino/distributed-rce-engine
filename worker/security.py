import ast

"""
This module acts as a "Pre-computation Linter" (Heuristic Analysis).
It scans code for forbidden keywords to reject obviously malicious scripts 
FAST, saving the compute cost of spinning up a container.

REAL security (isolation) is provided by the Kernel (Seccomp/Cgroups/Namespaces) 
in the execution engine ('run_container.py').
"""

FORBIDDEN_IMPORTS = {
    "os", "subprocess", "shutil", "socket", "requests", "urllib", 
    "pickle", "sys", "importlib", "pathlib", "ftplib"
}

FORBIDDEN_FUNCTIONS = {
    "exec", "eval", "compile", "open", "input", "__import__", "breakpoint"
}

class SecurityVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.errors = []
        
    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            # Split to handle 'os.path'
            if alias.name.split('.')[0] in FORBIDDEN_IMPORTS:
                self.errors.append(f"Security Violation: Import '{alias.name}' is forbidden.")
        self.generic_visit(node)
    
    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module and node.module.split('.')[0] in FORBIDDEN_IMPORTS:
            self.errors.append(f"Security Violation: From-Import '{node.module}' is forbidden.")
        self.generic_visit(node)
        
    def visit_Call(self, node: ast.Call):
        # Handle func() calls
        if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_FUNCTIONS:
            self.errors.append(f"Security Violation: Function '{node.func.id}()' is forbidden.")
        self.generic_visit(node)
    
def scan_code(code_bytes: bytes):
    """
    Statically analyzes code AST for forbidden patterns.
    Returns True if safe, raises ValueError if violations found.
    """
    
    try:
        code_str = code_bytes.decode('utf-8')
        tree = ast.parse(code_str)
    except SyntaxError as e:
        raise ValueError(f"Syntax Error in script: {e}")
    
    visitor = SecurityVisitor()
    visitor.visit(tree)
    
    if visitor.errors:
        raise ValueError("\n".join(visitor.errors))
    
    return True