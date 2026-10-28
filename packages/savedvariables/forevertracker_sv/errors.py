class SavedVariablesError(ValueError):
    """Raised when a SavedVariables file is malformed, exceeds limits, or is not a ForeverTracker export."""

    def __init__(self, message: str, *, line: int | None = None):
        self.line = line
        super().__init__(f"{message} (line {line})" if line is not None else message)
