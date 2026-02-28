"""LangGraph workflow definitions for the Suno AI agent.

Three workflows:
  - mastering_workflow: Create -> Master -> Export pipeline
  - batch_workflow: Process a list of SongSpecs through the full pipeline
  - interactive_workflow: ReAct agent loop for freeform commands
"""
import asyncio
import operator
from typing import Annotated, Any, Literal, Optional, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import create_react_agent
from rich.console import Console

from .llm_config import resolve_llm
from .tools import (
    ALL_TOOLS, set_browser,
    navigate_to, take_screenshot, get_studio_state, select_track,
    master_track, master_all_tracks, list_mastering_profiles,
    set_eq_band, set_eq_preset, create_song, export_song,
    set_track_volume, set_track_pan,
)
from ..browser import BrowserController

console = Console()


# --- State definitions ---

class MasteringState(TypedDict):
    """State for the mastering workflow."""
    profile: str
    export_type: Optional[str]
    track_count: int
    current_track: int
    results: Annotated[list[str], operator.add]
    status: str  # pending, mastering, exporting, done, error


class BatchState(TypedDict):
    """State for the batch workflow."""
    songs: list[dict]  # List of {lyrics, styles, title, weirdness, style_influence}
    profile: str  # Mastering profile to apply after creation
    export_type: Optional[str]
    current_index: int
    results: Annotated[list[str], operator.add]
    status: str  # pending, creating, mastering, exporting, done, error
    wait_between: int


class InteractiveState(TypedDict):
    """State for the interactive ReAct agent."""
    messages: Annotated[list, operator.add]


# --- Mastering workflow ---

def build_mastering_workflow(browser: BrowserController) -> StateGraph:
    """Build a LangGraph workflow for mastering all tracks + optional export.

    Flow: navigate_studio -> get_tracks -> master_each -> export? -> done
    """
    set_browser(browser)

    async def navigate_studio(state: MasteringState) -> MasteringState:
        result = await navigate_to.ainvoke({"page": "studio"})
        return {"results": [f"Navigation: {result}"], "status": "mastering"}

    async def get_tracks(state: MasteringState) -> MasteringState:
        info = await get_studio_state.ainvoke({})
        # Parse track count from result
        lines = info.split("\n")
        count = 0
        for line in lines:
            if line.startswith("Tracks:"):
                try:
                    count = int(line.split(":")[1].strip())
                except ValueError:
                    pass
        return {"track_count": count, "current_track": 0, "results": [f"Found {count} tracks"]}

    async def master_next(state: MasteringState) -> MasteringState:
        track_num = state["current_track"] + 1  # 1-based for the tool
        profile = state["profile"]
        result = await master_track.ainvoke({"track_number": track_num, "profile": profile})
        return {
            "current_track": state["current_track"] + 1,
            "results": [result],
        }

    def should_continue_mastering(state: MasteringState) -> Literal["master_next", "check_export"]:
        if state["current_track"] < state["track_count"]:
            return "master_next"
        return "check_export"

    async def check_export(state: MasteringState) -> MasteringState:
        if state.get("export_type"):
            return {"status": "exporting"}
        return {"status": "done"}

    def should_export(state: MasteringState) -> Literal["do_export", "done"]:
        if state["status"] == "exporting":
            return "do_export"
        return "done"

    async def do_export(state: MasteringState) -> MasteringState:
        result = await export_song.ainvoke({"export_type": state.get("export_type", "full")})
        return {"results": [f"Export: {result}"], "status": "done"}

    async def done(state: MasteringState) -> MasteringState:
        ok = sum(1 for r in state["results"] if "Mastered" in r or "Applied" in r)
        total = state["track_count"]
        return {"results": [f"Complete: {ok}/{total} tracks mastered"], "status": "done"}

    # Build the graph
    workflow = StateGraph(MasteringState)

    workflow.add_node("navigate_studio", navigate_studio)
    workflow.add_node("get_tracks", get_tracks)
    workflow.add_node("master_next", master_next)
    workflow.add_node("check_export", check_export)
    workflow.add_node("do_export", do_export)
    workflow.add_node("done", done)

    workflow.set_entry_point("navigate_studio")
    workflow.add_edge("navigate_studio", "get_tracks")
    workflow.add_conditional_edges("get_tracks", should_continue_mastering)
    workflow.add_conditional_edges("master_next", should_continue_mastering)
    workflow.add_conditional_edges("check_export", should_export)
    workflow.add_edge("do_export", "done")
    workflow.add_edge("done", END)

    return workflow.compile()


# --- Batch workflow ---

def build_batch_workflow(browser: BrowserController) -> StateGraph:
    """Build a LangGraph workflow for batch song creation + mastering + export.

    Flow: create_next_song -> wait -> (loop) -> master_all -> export? -> done
    """
    set_browser(browser)

    async def create_next(state: BatchState) -> BatchState:
        idx = state["current_index"]
        song = state["songs"][idx]
        result = await create_song.ainvoke({
            "lyrics": song["lyrics"],
            "styles": song["styles"],
            "title": song.get("title"),
            "weirdness": song.get("weirdness"),
            "style_influence": song.get("style_influence"),
        })
        return {
            "current_index": idx + 1,
            "results": [f"Song {idx + 1}: {result}"],
            "status": "creating",
        }

    def should_continue_creating(state: BatchState) -> Literal["create_next", "do_mastering"]:
        if state["current_index"] < len(state["songs"]):
            return "create_next"
        return "do_mastering"

    async def do_mastering(state: BatchState) -> BatchState:
        if not state.get("profile"):
            return {"status": "exporting", "results": ["Skipped mastering (no profile)"]}

        result = await master_all_tracks.ainvoke({"profile": state["profile"]})
        return {"results": [f"Mastering: {result}"], "status": "exporting"}

    def should_export(state: BatchState) -> Literal["do_export", "done"]:
        if state.get("export_type"):
            return "do_export"
        return "done"

    async def do_export(state: BatchState) -> BatchState:
        result = await export_song.ainvoke({"export_type": state.get("export_type", "full")})
        return {"results": [f"Export: {result}"], "status": "done"}

    async def done(state: BatchState) -> BatchState:
        return {"results": ["Batch complete"], "status": "done"}

    workflow = StateGraph(BatchState)

    workflow.add_node("create_next", create_next)
    workflow.add_node("do_mastering", do_mastering)
    workflow.add_node("do_export", do_export)
    workflow.add_node("done", done)

    workflow.set_entry_point("create_next")
    workflow.add_conditional_edges("create_next", should_continue_creating)
    workflow.add_conditional_edges("do_mastering", should_export)
    workflow.add_edge("do_export", "done")
    workflow.add_edge("done", END)

    return workflow.compile()


# --- Interactive (ReAct) workflow ---

SUNO_SYSTEM_PROMPT = """You are an AI assistant that helps users create, master, and export music on Suno AI.

You have access to tools that control the Suno Studio browser interface. You can:
- Navigate to different pages (Studio, Create, Library)
- Create songs with lyrics and styles
- Apply mastering profiles to tracks (EQ presets + per-band tweaks)
- Adjust individual EQ bands, volume, and pan
- Export projects as WAV files
- Take screenshots to verify the current state

Available mastering profiles: radio_ready, warm_vinyl, bass_heavy, vocal_focus, bright_pop, lo_fi, clarity, flat

When the user asks you to do something:
1. First check the current state with get_studio_state or take_screenshot
2. Navigate to the right page if needed
3. Execute the requested action
4. Verify the result

Be concise in your responses. Report what you did and the outcome."""


def build_interactive_workflow(
    browser: BrowserController,
    llm: Optional[BaseChatModel] = None,
) -> Any:
    """Build a ReAct agent for interactive freeform commands.

    This is the most flexible workflow - the LLM decides which tools to
    call based on natural language input.
    """
    set_browser(browser)
    llm = llm or resolve_llm()

    agent = create_react_agent(
        model=llm,
        tools=ALL_TOOLS,
        prompt=SystemMessage(content=SUNO_SYSTEM_PROMPT),
    )

    return agent


# --- Convenience runners ---

async def run_mastering(
    browser: BrowserController,
    profile: str = "radio_ready",
    export_type: Optional[str] = None,
) -> list[str]:
    """Run the mastering workflow and return results."""
    workflow = build_mastering_workflow(browser)
    initial_state: MasteringState = {
        "profile": profile,
        "export_type": export_type,
        "track_count": 0,
        "current_track": 0,
        "results": [],
        "status": "pending",
    }
    final = await workflow.ainvoke(initial_state)
    return final["results"]


async def run_batch(
    browser: BrowserController,
    songs: list[dict],
    profile: str = "radio_ready",
    export_type: Optional[str] = None,
    wait_between: int = 60,
) -> list[str]:
    """Run the batch workflow and return results."""
    workflow = build_batch_workflow(browser)
    initial_state: BatchState = {
        "songs": songs,
        "profile": profile,
        "export_type": export_type,
        "current_index": 0,
        "results": [],
        "status": "pending",
        "wait_between": wait_between,
    }
    final = await workflow.ainvoke(initial_state)
    return final["results"]


async def run_interactive(
    browser: BrowserController,
    message: str,
    llm: Optional[BaseChatModel] = None,
    history: Optional[list] = None,
) -> tuple[str, list]:
    """Run a single interactive turn and return (response, updated_history)."""
    agent = build_interactive_workflow(browser, llm)

    messages = history or []
    messages.append(HumanMessage(content=message))

    result = await agent.ainvoke({"messages": messages})

    updated_messages = result["messages"]
    # Get the final AI response
    ai_response = ""
    for msg in reversed(updated_messages):
        if isinstance(msg, AIMessage) and msg.content:
            ai_response = msg.content
            break

    return ai_response, updated_messages
