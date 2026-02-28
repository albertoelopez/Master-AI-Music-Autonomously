"""LLM provider resolver for the Suno AI agent.

Supports DeepSeek, Ollama, OpenAI, and Anthropic via LangChain.
Reads defaults from config/agent_config.yaml, overridable at runtime.
"""
import os
import yaml
from typing import Optional

from langchain_core.language_models.chat_models import BaseChatModel

# Path to the YAML config
_CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "config")
_CONFIG_PATH = os.path.join(_CONFIG_DIR, "agent_config.yaml")


def load_agent_config() -> dict:
    """Load agent configuration from YAML."""
    if os.path.exists(_CONFIG_PATH):
        with open(_CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}


def resolve_llm(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    **kwargs,
) -> BaseChatModel:
    """Resolve an LLM instance from provider name and model.

    Falls back to config/agent_config.yaml defaults, then to DeepSeek.

    Args:
        provider: LLM provider (deepseek, ollama, openai, anthropic)
        model: Model name/ID
        temperature: Sampling temperature
        api_key: API key (overrides env var)
        base_url: Custom API base URL
        **kwargs: Extra kwargs passed to the LangChain model constructor

    Returns:
        A LangChain BaseChatModel instance
    """
    config = load_agent_config()
    llm_config = config.get("llm", {})

    provider = provider or llm_config.get("provider", "deepseek")
    model = model or llm_config.get("model", "deepseek-chat")
    temperature = temperature if temperature is not None else llm_config.get("temperature", 0.1)

    # Resolve API key from explicit arg, env var name in config, or standard env vars
    if not api_key:
        env_var = llm_config.get("api_key_env", "")
        if env_var:
            api_key = os.environ.get(env_var)

    provider = provider.lower()

    if provider == "deepseek":
        from langchain_deepseek import ChatDeepSeek

        api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        return ChatDeepSeek(
            model=model,
            temperature=temperature,
            api_key=api_key,
            **({"base_url": base_url} if base_url else {}),
            **kwargs,
        )

    elif provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=model,
            temperature=temperature,
            **({"base_url": base_url} if base_url else {}),
            **kwargs,
        )

    elif provider == "openai":
        try:
            from langchain_openai import ChatOpenAI
        except ImportError:
            raise ImportError(
                "langchain-openai is required for the OpenAI provider. "
                "Install it with: pip install langchain-openai"
            )

        api_key = api_key or os.environ.get("OPENAI_API_KEY")
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            api_key=api_key,
            **({"base_url": base_url} if base_url else {}),
            **kwargs,
        )

    elif provider == "anthropic":
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError:
            raise ImportError(
                "langchain-anthropic is required for the Anthropic provider. "
                "Install it with: pip install langchain-anthropic"
            )

        api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        return ChatAnthropic(
            model=model,
            temperature=temperature,
            api_key=api_key,
            **kwargs,
        )

    else:
        raise ValueError(
            f"Unknown LLM provider: {provider}. "
            f"Supported: deepseek, ollama, openai, anthropic"
        )


def resolve_browser_use_llm(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    **kwargs,
):
    """Resolve a browser-use native LLM instance (NOT LangChain).

    Browser-use 0.12+ has its own LLM wrappers (ChatOllama, ChatOpenAI, etc.)
    that are required by the Agent class. LangChain models will NOT work.

    Returns:
        A browser-use compatible LLM instance
    """
    config = load_agent_config()
    llm_config = config.get("llm", {})

    provider = (provider or llm_config.get("provider", "ollama")).lower()
    model = model or llm_config.get("model", "llama3.1:8b")
    temperature = temperature if temperature is not None else llm_config.get("temperature", 0.1)

    if not api_key:
        env_var = llm_config.get("api_key_env", "")
        if env_var:
            api_key = os.environ.get(env_var)

    if provider == "ollama":
        from browser_use import ChatOllama as BUChatOllama
        return BUChatOllama(model=model, temperature=temperature, **kwargs)

    elif provider == "openai":
        from browser_use import ChatOpenAI as BUChatOpenAI
        api_key = api_key or os.environ.get("OPENAI_API_KEY")
        return BUChatOpenAI(
            model=model, temperature=temperature, api_key=api_key,
            **({"base_url": base_url} if base_url else {}), **kwargs,
        )

    elif provider == "deepseek":
        from browser_use import ChatOpenAI as BUChatOpenAI
        api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        return BUChatOpenAI(
            model=model, temperature=temperature, api_key=api_key,
            base_url=base_url or "https://api.deepseek.com/v1", **kwargs,
        )

    elif provider == "anthropic":
        from browser_use import ChatAnthropic as BUChatAnthropic
        api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        return BUChatAnthropic(
            model=model, temperature=temperature, api_key=api_key, **kwargs,
        )

    elif provider == "google":
        from browser_use import ChatGoogle as BUChatGoogle
        api_key = api_key or os.environ.get("GOOGLE_API_KEY")
        return BUChatGoogle(model=model, temperature=temperature, api_key=api_key, **kwargs)

    else:
        raise ValueError(
            f"Unknown browser-use LLM provider: {provider}. "
            f"Supported: ollama, openai, deepseek, anthropic, google"
        )


def get_browser_config() -> dict:
    """Get browser configuration from YAML."""
    config = load_agent_config()
    return config.get("browser", {
        "cdp_port": 9222,
        "headless": False,
        "user_data_dir": "browser_data/",
        "viewport": {"width": 1280, "height": 900},
    })


def get_autonomy_config() -> dict:
    """Get autonomy level configuration from YAML."""
    config = load_agent_config()
    return config.get("autonomy", {
        "default_level": "supervised",
        "page_overrides": {},
    })


def get_ui_config() -> dict:
    """Get UI configuration from YAML."""
    config = load_agent_config()
    return config.get("ui", {"type": "gradio", "port": 7860})
