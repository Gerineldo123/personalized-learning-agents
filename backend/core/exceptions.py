class AppException(Exception):
    def __init__(self, message: str, code: int = 400):
        self.message = message
        self.code = code


class AgentNotFoundError(AppException):
    def __init__(self, agent_name: str):
        super().__init__(f"智能体 {agent_name} 未注册", 404)
