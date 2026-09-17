"""应用配置。"""

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _read_first_env(*names: str, default: str = "") -> str:
    """按优先级读取非空环境变量，方便兼容常见 OpenAI 配置名。"""

    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return default


def _read_project_path_env(name: str, default: str) -> str:
    """读取项目路径配置，确保相对路径不受启动目录影响。"""

    value = os.getenv(name, "").strip() or default
    path = Path(value)
    return str(path if path.is_absolute() else PROJECT_ROOT / path)


@dataclass(frozen=True)
class Settings:
    """从环境变量读取的配置。"""

    llm_api_key: str = _read_first_env("LLM_API_KEY", "OPENAI_API_KEY")
    llm_base_url: str = _read_first_env(
        "LLM_BASE_URL",
        "LOCAL_LLM_BASE_URL",
        "OPENAI_BASE_URL",
        default="",
    )
    llm_model: str = _read_first_env(
        "LLM_MODEL",
        "LOCAL_LLM_MODEL",
        "OPENAI_MODEL",
        default="",
    )
    llm_wire_api: str = _read_first_env(
        "LLM_WIRE_API", "OPENAI_WIRE_API", default="responses"
    ).lower()
    llm_reasoning_effort: str = _read_first_env(
        "LLM_REASONING_EFFORT",
        "MODEL_REASONING_EFFORT",
        default="low",
    ).lower()
    llm_max_output_tokens: int = int(
        _read_first_env("LLM_MAX_OUTPUT_TOKENS", default="4096")
    )
    llm_fallback_api_key: str = _read_first_env(
        "LLM_FALLBACK_API_KEY",
        "TOKENRHYTHM_API_KEY",
        default="",
    )
    llm_fallback_base_url: str = _read_first_env(
        "LLM_FALLBACK_BASE_URL",
        "TOKENRHYTHM_BASE_URL",
        default="https://tokenrhythm.studio/v1",
    )
    llm_fallback_model: str = _read_first_env(
        "LLM_FALLBACK_MODEL",
        "TOKENRHYTHM_MODEL",
        default="deepseek-v4-flash",
    )
    database_path: str = _read_project_path_env(
        "DATABASE_PATH", str(PROJECT_ROOT / "data" / "fun_research.db")
    )
    request_timeout: int = int(os.getenv("REQUEST_TIMEOUT", "120"))
    frontend_origin: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
    admin_password: str = os.getenv("ADMIN_PASSWORD", "10124")

    @property
    def has_llm(self) -> bool:
        """判断真实大模型 API 配置是否完整。"""

        return bool(self.llm_api_key and self.llm_base_url and self.llm_model)

    @property
    def has_llm_fallback(self) -> bool:
        """判断基元律动兜底接口配置是否完整。"""

        return bool(
            self.llm_fallback_api_key
            and self.llm_fallback_base_url
            and self.llm_fallback_model
        )

    @property
    def is_local_llm(self) -> bool:
        """判断当前地址是否为本机模型服务。"""

        hostname = urlparse(self.llm_base_url).hostname
        return hostname in {"localhost", "127.0.0.1", "::1"}


settings = Settings()
