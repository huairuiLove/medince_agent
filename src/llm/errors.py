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


class DrugSearchModelNotReadyError(RuntimeError):
    """Raised when semantic drug search model/index is unavailable."""

    def __init__(self, detail: str = "", hint: str = "") -> None:
        msg = "Drug catalog semantic search is not ready."
        if detail:
            msg = f"{msg} {detail}"
        if hint:
            msg = f"{msg} {hint}"
        super().__init__(msg)


class DdiModelNotReadyError(RuntimeError):
    """Raised when Bio_ClinicalBERT DDI model is required but missing or failed to load."""

    def __init__(self, detail: str = "", hint: str = "") -> None:
        msg = (
            "DDI-BERT 未就绪：safety_models.ddi_bert 已启用，但模型无法加载。"
            "禁止静默跳过 DDI 推断。"
        )
        if detail:
            msg = f"{msg} {detail}"
        if hint:
            msg = f"{msg} {hint}"
        else:
            msg = f"{msg} 请运行: python scripts/download_models.py --ddi-bert"
        super().__init__(msg)


class VisionLLMError(RuntimeError):
    """Raised when Qwen VLM upstream call fails (auth, quota, timeout, etc.)."""

    def __init__(
        self,
        service: str,
        detail: str = "",
        *,
        status_code: int | None = None,
        hint: str = "",
    ) -> None:
        msg = f"{service} 调用失败"
        if detail:
            msg = f"{msg}：{detail}"
        if hint:
            msg = f"{msg} {hint}"
        super().__init__(msg)
        self.service = service
        self.status_code = status_code
