"""Suno AI Agent - LLM-driven browser automation.

Layers:
  - llm_config: Multi-provider LLM resolver (DeepSeek, Ollama, OpenAI, Anthropic)
  - tools: LangChain @tool wrappers around existing Suno skills
  - browser_use_agent: Browser Use integration for intelligent navigation
  - workflows: LangGraph StateGraph workflows (mastering, batch, interactive)
"""
from .llm_config import resolve_llm, resolve_browser_use_llm, load_agent_config
from .browser_use_agent import SunoBrowserAgent
from .workflows import (
    run_mastering, run_batch, run_interactive,
    build_mastering_workflow, build_batch_workflow, build_interactive_workflow,
)

__all__ = [
    "resolve_llm",
    "resolve_browser_use_llm",
    "load_agent_config",
    "SunoBrowserAgent",
    "run_mastering",
    "run_batch",
    "run_interactive",
    "build_mastering_workflow",
    "build_batch_workflow",
    "build_interactive_workflow",
]
