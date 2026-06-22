"""LLM configuration errors — no mock / placeholder responses."""


class LLMNotConfiguredError(RuntimeError):
    """Raised when a real LLM API key or provider is required but missing."""

    def __init__(self, service: str, hint: str = "") -> None:
        msg = (
            f"{service} 未配置：本项目禁止使用 Mock 或假数据。"
            "请在 config.yaml 或环境变量中设置有效的 API Key 与 provider。"
        )
        if hint:
            msg = f"{msg} {hint}"
        super().__init__(msg)
        self.service = service
