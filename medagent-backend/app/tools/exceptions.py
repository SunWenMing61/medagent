class ToolPolicyDenied(PermissionError):
    pass


class ToolCircuitOpen(RuntimeError):
    pass


class ToolExecutionTimeout(TimeoutError):
    pass
