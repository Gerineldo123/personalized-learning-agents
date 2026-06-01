from core.exceptions import AgentNotFoundError

_registry: dict[str, "BaseAgent"] = {}


def register(agent: "BaseAgent"):
    _registry[agent.name] = agent


def get_agent(name: str):
    if name not in _registry:
        raise AgentNotFoundError(name)
    return _registry[name]


def get_all_agents():
    return list(_registry.values())


def reset():
    _registry.clear()
