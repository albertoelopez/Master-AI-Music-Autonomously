"""Hybrid v1 autopilot: planner + deterministic executor + checkpointing."""
import asyncio
import json
import os
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from rich.console import Console
from rich.table import Table

from ..browser import BrowserController
from ..skills import ModalSkill, NavigateSkill
from .batch_create import BatchCreateAgent, SongSpec
from .mastering import MasteringAgent

console = Console()


GENRE_PRESETS = {
    "pop": {
        "styles": "modern pop, catchy hooks, polished production, radio-ready",
        "profile": "radio_ready",
        "weirdness": 35,
        "influence": 75,
        "imagery": ["city lights", "late-night drive", "heartbeat", "neon skyline"],
    },
    "edm": {
        "styles": "EDM, festival energy, heavy drops, sidechain pumping, bright synths",
        "profile": "bass_heavy",
        "weirdness": 45,
        "influence": 80,
        "imagery": ["strobe lights", "crowd jump", "bassline", "laser beams"],
    },
    "lofi": {
        "styles": "lo-fi hip hop, dusty drums, vinyl crackle, mellow keys, chill",
        "profile": "lo_fi",
        "weirdness": 25,
        "influence": 60,
        "imagery": ["rainy window", "old notebook", "coffee steam", "faded photo"],
    },
    "rock": {
        "styles": "alternative rock, driven guitars, live drums, anthemic chorus",
        "profile": "clarity",
        "weirdness": 40,
        "influence": 70,
        "imagery": ["highway", "amp glow", "crowd chant", "midnight road"],
    },
    "hiphop": {
        "styles": "hip-hop, punchy drums, deep 808, confident flow, modern trap influence",
        "profile": "bass_heavy",
        "weirdness": 50,
        "influence": 78,
        "imagery": ["streetlights", "skyscraper", "808 rumble", "night ambition"],
    },
    "rnb": {
        "styles": "R&B, smooth vocals, warm keys, groove-focused, soulful",
        "profile": "vocal_focus",
        "weirdness": 30,
        "influence": 72,
        "imagery": ["velvet room", "moonlight", "silk chords", "slow pulse"],
    },
}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "track"


def _pick_preset(music_type: str) -> dict:
    key = _slug(music_type).replace("_", "")
    for preset_key in GENRE_PRESETS:
        if preset_key in key:
            return GENRE_PRESETS[preset_key]
    return {
        "styles": f"{music_type}, modern production, emotionally engaging",
        "profile": "radio_ready",
        "weirdness": 40,
        "influence": 70,
        "imagery": ["night sky", "heartbeat", "motion", "echo"],
    }


class SpecPlanner:
    """Simple planning layer that converts intent into concrete song specs."""

    def generate(self, music_type: str, index: int) -> tuple[SongSpec, str]:
        preset = _pick_preset(music_type)
        images = random.sample(preset["imagery"], k=min(3, len(preset["imagery"])))
        title = f"{music_type.title()} Session {index + 1}"
        lyrics = (
            f"[Verse 1]\n"
            f"{images[0].title()} in the distance, we don't look back tonight\n"
            f"We turn the pressure into motion, turn the silence into light\n\n"
            f"[Chorus]\n"
            f"This is our {music_type} moment, loud and clear\n"
            f"We rise together, no fear\n"
            f"From {images[1]} to {images[2]}, we keep it true\n"
            f"One more song to break through\n\n"
            f"[Outro]\n"
            f"Keep it moving, keep it true."
        )
        spec = SongSpec(
            lyrics=lyrics,
            styles=preset["styles"],
            title=title,
            weirdness=preset["weirdness"],
            style_influence=preset["influence"],
        )
        return spec, preset["profile"]


class DspySpecPlanner:
    """DSPy-backed planner with template fallback contract."""

    def __init__(self, model: Optional[str] = None):
        self.model = model or os.getenv("DSPY_MODEL")
        self._dspy = None
        self._predict = None
        self._err: Optional[str] = None
        self._setup()

    def _setup(self):
        try:
            import dspy  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dependency
            self._err = f"DSPy import failed: {exc}"
            return

        if not self.model:
            self._err = "DSPY_MODEL is not set and no --dspy-model was provided"
            return

        try:
            lm = dspy.LM(self.model)
            dspy.configure(lm=lm)
            self._predict = dspy.Predict(
                "music_type, iteration -> title, lyrics, styles, weirdness, style_influence, mastering_profile"
            )
            self._dspy = dspy
        except Exception as exc:  # pragma: no cover - provider/env specific
            self._err = f"DSPy setup failed: {exc}"

    @property
    def ready(self) -> bool:
        return self._predict is not None

    @property
    def error(self) -> Optional[str]:
        return self._err

    def generate(self, music_type: str, index: int) -> tuple[SongSpec, str]:
        if not self.ready:
            raise RuntimeError(self._err or "DSPy planner unavailable")

        result = self._predict(
            music_type=music_type,
            iteration=index + 1,
        )
        profile_raw = str(getattr(result, "mastering_profile", "radio_ready")).strip().lower()
        profile = profile_raw if profile_raw in {
            "radio_ready", "warm_vinyl", "bass_heavy", "vocal_focus", "bright_pop", "lo_fi", "clarity", "flat"
        } else "radio_ready"

        spec = SongSpec(
            lyrics=str(getattr(result, "lyrics", "")).strip() or f"{music_type} instrumental",
            styles=str(getattr(result, "styles", "")).strip() or music_type,
            title=str(getattr(result, "title", f'{music_type.title()} Session {index + 1}')).strip(),
            weirdness=max(0, min(100, int(getattr(result, "weirdness", 40) or 40))),
            style_influence=max(0, min(100, int(getattr(result, "style_influence", 70) or 70))),
        )
        return spec, profile


class Phase2PlannerCoordinator:
    """BMAD-style phased planning with Gastown-style parallel candidates."""

    def __init__(self, planner: Any):
        self.planner = planner

    @staticmethod
    def _score_spec(spec: SongSpec) -> float:
        score = 0.0
        if spec.title and len(spec.title) >= 6:
            score += 1.0
        if spec.styles and 20 <= len(spec.styles) <= 180:
            score += 1.5
        if spec.lyrics and len(spec.lyrics) >= 120:
            score += 2.0
        if spec.weirdness is not None:
            score += 0.75 if 10 <= spec.weirdness <= 80 else 0.2
        if spec.style_influence is not None:
            score += 0.75 if 40 <= spec.style_influence <= 90 else 0.2
        return score

    async def build_plan(
        self,
        music_type: str,
        index: int,
        candidate_count: int,
    ) -> tuple[SongSpec, str, list[dict[str, Any]]]:
        artifacts: list[dict[str, Any]] = []
        artifacts.append(
            {
                "phase": "discover",
                "music_type": music_type,
                "index": index,
                "objective": "create-master-export one song with autonomous settings",
            }
        )

        # Parallel candidate generation (Gastown-style worker fanout).
        tasks = [
            asyncio.to_thread(self.planner.generate, music_type, index + i)
            for i in range(max(1, candidate_count))
        ]
        candidate_results = await asyncio.gather(*tasks, return_exceptions=True)

        candidates: list[dict[str, Any]] = []
        for i, item in enumerate(candidate_results, start=1):
            if isinstance(item, Exception):
                candidates.append(
                    {
                        "candidate": i,
                        "error": str(item),
                        "score": -1.0,
                    }
                )
                continue
            spec, profile = item
            score = self._score_spec(spec)
            candidates.append(
                {
                    "candidate": i,
                    "spec": {
                        "lyrics": spec.lyrics,
                        "styles": spec.styles,
                        "title": spec.title,
                        "weirdness": spec.weirdness,
                        "style_influence": spec.style_influence,
                    },
                    "profile": profile,
                    "score": score,
                }
            )

        artifacts.append(
            {
                "phase": "design",
                "candidate_count": len(candidates),
                "candidates": candidates,
            }
        )

        valid = [c for c in candidates if "spec" in c]
        if not valid:
            raise RuntimeError("phase2 planning failed: no valid candidates generated")

        best = max(valid, key=lambda c: c["score"])
        selected_spec = SongSpec(**best["spec"])
        selected_profile = best["profile"]

        artifacts.append(
            {
                "phase": "decide",
                "selected_candidate": best["candidate"],
                "selected_score": best["score"],
                "selected_profile": selected_profile,
                "selected_title": selected_spec.title,
            }
        )
        return selected_spec, selected_profile, artifacts


@dataclass
class AutopilotConfig:
    """Runtime settings for hybrid autopilot."""
    music_type: str
    count: int = 1
    wait_generation: int = 90
    wait_between: int = 20
    export_type: str = "full"
    step_retries: int = 2
    checkpoint_file: str = "/tmp/suno_autopilot_checkpoint.json"
    resume: bool = False
    continue_on_error: bool = True
    planner: str = "auto"  # auto|template|dspy
    dspy_model: Optional[str] = None
    phase2: bool = False
    candidate_count: int = 3
    phase2_artifact_log: str = "/tmp/suno_phase2_artifacts.jsonl"
    pause_on_captcha: bool = True
    resume_file: str = "/tmp/suno_autopilot.resume"
    event_log: str = "/tmp/suno_autopilot_events.jsonl"


@dataclass
class AutopilotState:
    """Persistent state for resumable runs."""
    song_index: int = 0
    phase: str = "plan"  # plan -> create -> wait -> master_export -> done
    profile: str = "radio_ready"
    spec: Optional[dict[str, Any]] = None
    last_error: Optional[str] = None


class AutopilotAgent:
    """Hybrid runner: planner chooses spec, executor performs browser actions."""

    def __init__(self, browser: BrowserController):
        self.browser = browser
        self.nav = NavigateSkill(browser)
        self.modal = ModalSkill(browser)
        self.create_agent = BatchCreateAgent(browser)
        self.mastering_agent = MasteringAgent(browser)
        self.planner: Any = SpecPlanner()
        self.rows: list[tuple[int, str, str, str]] = []

    async def initialize(self) -> bool:
        if not await self.browser.connect():
            return False
        await self.nav.to_create()
        await self.modal.dismiss_all()
        login = await self.nav.is_logged_in()
        if not login.success:
            console.print(f"[yellow]Not logged in: {login.message}[/yellow]")
            return False
        return True

    def _select_planner(self, config: AutopilotConfig):
        if config.planner == "template":
            self.planner = SpecPlanner()
            console.print("[cyan]Planner:[/cyan] template")
            return

        if config.planner in ("dspy", "auto"):
            dspy_planner = DspySpecPlanner(model=config.dspy_model)
            if dspy_planner.ready:
                self.planner = dspy_planner
                console.print(f"[cyan]Planner:[/cyan] dspy ({dspy_planner.model})")
                return
            if config.planner == "dspy":
                raise RuntimeError(dspy_planner.error or "DSPy planner failed to initialize")
            console.print(f"[yellow]DSPy unavailable, fallback to template planner: {dspy_planner.error}[/yellow]")

        self.planner = SpecPlanner()
        console.print("[cyan]Planner:[/cyan] template")

    def _checkpoint_path(self, config: AutopilotConfig) -> Path:
        path = Path(config.checkpoint_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _save_checkpoint(self, config: AutopilotConfig, state: AutopilotState):
        payload = {
            "music_type": config.music_type,
            "count": config.count,
            "wait_generation": config.wait_generation,
            "wait_between": config.wait_between,
            "export_type": config.export_type,
            "song_index": state.song_index,
            "phase": state.phase,
            "profile": state.profile,
            "spec": state.spec,
            "last_error": state.last_error,
        }
        self._checkpoint_path(config).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _load_checkpoint(self, config: AutopilotConfig) -> Optional[AutopilotState]:
        path = self._checkpoint_path(config)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("music_type") != config.music_type:
                return None
            return AutopilotState(
                song_index=int(payload.get("song_index", 0)),
                phase=payload.get("phase", "plan"),
                profile=payload.get("profile", "radio_ready"),
                spec=payload.get("spec"),
                last_error=payload.get("last_error"),
            )
        except Exception:
            return None

    def _clear_checkpoint(self, config: AutopilotConfig):
        path = self._checkpoint_path(config)
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass

    def _append_phase2_artifacts(self, config: AutopilotConfig, artifacts: list[dict[str, Any]]):
        if not artifacts:
            return
        path = Path(config.phase2_artifact_log)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            for a in artifacts:
                f.write(json.dumps(a) + "\n")

    def _append_event(self, config: AutopilotConfig, event: dict[str, Any]):
        path = Path(config.event_log)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")

    async def _wait_for_resume_signal(self, config: AutopilotConfig):
        resume = Path(config.resume_file)
        console.print(
            f"[yellow]Paused for CAPTCHA. Solve challenge, then run:[/yellow] touch {config.resume_file}"
        )
        while True:
            await asyncio.sleep(2)
            if resume.exists():
                try:
                    resume.unlink()
                except OSError:
                    pass
                console.print("[green]Resume signal received.[/green]")
                return

    async def _run_step_with_retries(
        self,
        label: str,
        retries: int,
        fn: Callable[[], Any],
    ) -> tuple[bool, str]:
        max_attempts = retries + 1
        for attempt in range(1, max_attempts + 1):
            ok, msg = await fn()
            if ok:
                return True, msg
            if attempt < max_attempts:
                console.print(f"[yellow]{label} failed ({msg}). Retrying {attempt}/{retries}...[/yellow]")
                await asyncio.sleep(2)
        return False, msg

    async def _step_create(self, spec: SongSpec) -> tuple[bool, str]:
        await self.nav.to_create()
        await self.modal.dismiss_all()
        result = await self.create_agent.create_song(spec)
        return result.success, result.message

    async def _step_master_export(self, profile: str, export_type: str) -> tuple[bool, str]:
        await self.mastering_agent.initialize()
        results = await self.mastering_agent.master_and_export(profile=profile, export_type=export_type)
        if any(r.success for r in results):
            return True, f"mastered with {profile}, exported {export_type}"
        return False, "mastering returned no successful tracks"

    async def run(self, config: AutopilotConfig):
        self._select_planner(config)
        state = self._load_checkpoint(config) if config.resume else None
        if state:
            console.print(
                f"[cyan]Resuming from checkpoint[/cyan]: song={state.song_index + 1}, phase={state.phase}"
            )
        else:
            state = AutopilotState()
            self._save_checkpoint(config, state)

        while state.song_index < config.count:
            current_n = state.song_index + 1

            if state.phase == "plan":
                if config.phase2:
                    coordinator = Phase2PlannerCoordinator(self.planner)
                    spec, profile, artifacts = await coordinator.build_plan(
                        config.music_type,
                        state.song_index,
                        config.candidate_count,
                    )
                    self._append_phase2_artifacts(config, artifacts)
                else:
                    spec, profile = self.planner.generate(config.music_type, state.song_index)
                state.spec = {
                    "lyrics": spec.lyrics,
                    "styles": spec.styles,
                    "title": spec.title,
                    "weirdness": spec.weirdness,
                    "style_influence": spec.style_influence,
                }
                state.profile = profile
                state.last_error = None
                state.phase = "create"
                self._save_checkpoint(config, state)
                self._append_event(
                    config,
                    {
                        "event": "planned",
                        "song_index": state.song_index,
                        "title": spec.title,
                        "profile": profile,
                    },
                )
                console.print(
                    f"\n[bold]Planned {current_n}/{config.count}[/bold] "
                    f"title={spec.title} profile={profile}"
                )

            spec = SongSpec(**(state.spec or {}))

            if state.phase == "create":
                ok, msg = await self._run_step_with_retries(
                    "create",
                    config.step_retries,
                    lambda: self._step_create(spec),
                )
                if not ok:
                    state.last_error = msg
                    self.rows.append((current_n, spec.title or "-", "FAILED_CREATE", msg))
                    self._save_checkpoint(config, state)
                    self._append_event(
                        config,
                        {
                            "event": "create_failed",
                            "song_index": state.song_index,
                            "title": spec.title,
                            "message": msg,
                        },
                    )
                    if "captcha" in msg.lower():
                        if config.pause_on_captcha:
                            self._append_event(
                                config,
                                {
                                    "event": "captcha_pause",
                                    "song_index": state.song_index,
                                    "title": spec.title,
                                    "resume_file": config.resume_file,
                                },
                            )
                            await self._wait_for_resume_signal(config)
                            self._append_event(
                                config,
                                {
                                    "event": "captcha_resume",
                                    "song_index": state.song_index,
                                    "title": spec.title,
                                },
                            )
                            continue
                        console.print(
                            "[yellow]CAPTCHA blocked autopilot. Solve it in browser then rerun with --resume.[/yellow]"
                        )
                        break
                    if not config.continue_on_error:
                        break
                    state.song_index += 1
                    state.phase = "plan"
                    self._save_checkpoint(config, state)
                    continue
                state.phase = "wait"
                state.last_error = None
                self._save_checkpoint(config, state)

            if state.phase == "wait":
                if config.wait_generation > 0:
                    console.print(f"[dim]Waiting {config.wait_generation}s for generation...[/dim]")
                    await asyncio.sleep(config.wait_generation)
                state.phase = "master_export"
                self._save_checkpoint(config, state)

            if state.phase == "master_export":
                ok, msg = await self._run_step_with_retries(
                    "master_export",
                    config.step_retries,
                    lambda: self._step_master_export(state.profile, config.export_type),
                )
                if not ok:
                    state.last_error = msg
                    self.rows.append((current_n, spec.title or "-", "FAILED_MASTER_EXPORT", msg))
                    self._save_checkpoint(config, state)
                    self._append_event(
                        config,
                        {
                            "event": "master_export_failed",
                            "song_index": state.song_index,
                            "title": spec.title,
                            "message": msg,
                        },
                    )
                    if not config.continue_on_error:
                        break
                else:
                    self.rows.append((current_n, spec.title or "-", "OK", msg))
                    self._append_event(
                        config,
                        {
                            "event": "song_completed",
                            "song_index": state.song_index,
                            "title": spec.title,
                            "message": msg,
                        },
                    )

                state.song_index += 1
                state.phase = "plan"
                state.last_error = None
                self._save_checkpoint(config, state)

                if state.song_index < config.count and config.wait_between > 0:
                    await asyncio.sleep(config.wait_between)

        if state.song_index >= config.count:
            self._clear_checkpoint(config)
        self.show_summary()

    def show_summary(self):
        table = Table(title="Autopilot Summary")
        table.add_column("#", style="dim")
        table.add_column("Title", style="cyan")
        table.add_column("Status")
        table.add_column("Message", style="dim")
        for idx, title, status, msg in self.rows:
            status_cell = "[green]OK[/green]" if status == "OK" else f"[red]{status}[/red]"
            table.add_row(str(idx), title, status_cell, msg)
        console.print(table)
