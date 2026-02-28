"""EQ skills - 6-band parametric equalizer manipulation."""
import asyncio
from typing import Optional
from .base import Skill, SkillResult, console


# EQ presets available in Suno (verified Feb 28 2026)
EQ_PRESETS = [
    "Flat (Reset)", "Hi-Pass", "Vocal", "Warm", "Bright", "Presence",
    "Bass Boost", "Air", "Clarity", "Fullness", "Lo-Fi", "Modern"
]

# Band defaults (Flat preset)
BAND_DEFAULTS = {
    1: {"freq": "60Hz", "gain": "0.0dB", "q": "0.71", "filter": "High-pass"},
    2: {"freq": "200Hz", "gain": "0.0dB", "q": "0.71", "filter": "Bell"},
    3: {"freq": "450Hz", "gain": "0.0dB", "q": "0.71", "filter": "Bell"},
    4: {"freq": "2kHz", "gain": "0.0dB", "q": "0.71", "filter": "Bell"},
    5: {"freq": "6kHz", "gain": "0.0dB", "q": "0.71", "filter": "Bell"},
    6: {"freq": "8.8kHz", "gain": "0.0dB", "q": "0.71", "filter": "Low-pass"},
}

# Pixel positions from verified control map (calibrated Feb 28 2026)
EQ_POSITIONS = {
    "toggle": (1217, 283),
    "preset_prev": (1021, 359),   # Center of prev arrow
    "preset_button": (1121, 359),  # Center of preset name
    "preset_next": (1221, 359),   # Center of next arrow
    "canvas": (1121, 447),        # Center of EQ canvas
    "bands": {
        1: (1065, 565), 2: (1097, 565), 3: (1129, 565),
        4: (1161, 565), 5: (1193, 565), 6: (1225, 565),
    },
    "filter_types": {
        # Y=608, positions from control map
        0: (1021, 608), 1: (1061, 608), 2: (1101, 608),
        3: (1141, 608), 4: (1181, 608), 5: (1221, 608),
    },
    "knobs": {
        "freq": (1037, 660),
        "gain": (1121, 660),
        "res": (1205, 660),
    },
    "inputs": {
        "freq": (1037, 692),
        "gain": (1121, 692),
        "res": (1205, 692),
    },
}

FILTER_TYPE_NAMES = ["Bell/Peak", "High-pass", "Low-pass", "High-shelf", "Low-shelf", "Notch"]


class EQSkill(Skill):
    """Manipulate the 6-band parametric EQ on the Track tab."""

    async def enable(self) -> SkillResult:
        """Enable the EQ (toggle on)."""
        pos = EQ_POSITIONS["toggle"]
        # Check current state - look for switch near the EQ toggle position
        is_on = await self.browser.evaluate("""() => {
            const switches = document.querySelectorAll('[role=switch], button');
            for (const sw of switches) {
                const r = sw.getBoundingClientRect();
                if (Math.abs(r.x + r.width/2 - 1217) < 30 && Math.abs(r.y + r.height/2 - 283) < 30) {
                    return sw.getAttribute('aria-checked') === 'true' ||
                           sw.classList.contains('bg-blue') ||
                           sw.querySelector('[class*=bg-blue]') !== null;
                }
            }
            return null;
        }""")

        if is_on:
            return SkillResult(success=True, message="EQ already enabled")

        await self.click_at(pos[0], pos[1])
        return SkillResult(success=True, message="EQ enabled")

    async def disable(self) -> SkillResult:
        """Disable the EQ (toggle off)."""
        pos = EQ_POSITIONS["toggle"]
        await self.click_at(pos[0], pos[1])
        return SkillResult(success=True, message="EQ toggled")

    async def set_preset(self, preset_name: str) -> SkillResult:
        """Set an EQ preset by cycling through presets.

        Args:
            preset_name: One of the EQ_PRESETS names
        """
        if preset_name not in EQ_PRESETS:
            return SkillResult(success=False, message=f"Unknown preset: {preset_name}. Available: {EQ_PRESETS}")

        # First reset to Flat
        # Click prev arrow until we get to Flat (max 12 clicks)
        for _ in range(12):
            current = await self._get_current_preset()
            if current and "Flat" in current:
                break
            await self.click_at(*EQ_POSITIONS["preset_prev"])
            await self.wait(0.5)

        if preset_name.startswith("Flat"):
            return SkillResult(success=True, message="Set preset: Flat (Reset)")

        # Now click next until we reach target
        target_idx = EQ_PRESETS.index(preset_name)
        for _ in range(target_idx):
            await self.click_at(*EQ_POSITIONS["preset_next"])
            await self.wait(0.5)

        current = await self._get_current_preset()
        return SkillResult(success=True, message=f"Set preset: {current or preset_name}")

    async def select_band(self, band: int) -> SkillResult:
        """Select an EQ band (1-6)."""
        if band < 1 or band > 6:
            return SkillResult(success=False, message="Band must be 1-6")

        pos = EQ_POSITIONS["bands"][band]
        await self.click_at(pos[0], pos[1])
        return SkillResult(success=True, message=f"Selected band {band}")

    async def set_band(self, band: int, freq: Optional[str] = None,
                       gain: Optional[str] = None, q: Optional[str] = None) -> SkillResult:
        """Set EQ band parameters by typing into the input fields.

        Args:
            band: Band number 1-6
            freq: Frequency value (e.g. "200Hz", "2kHz", "8.5kHz")
            gain: Gain value (e.g. "3.0dB", "-2.5dB")
            q: Q/resonance value (e.g. "1.5", "0.5")
        """
        # Select the band first
        await self.select_band(band)
        await self.wait(0.5)

        results = []

        if freq is not None:
            await self.set_input_value(
                EQ_POSITIONS["inputs"]["freq"][0],
                EQ_POSITIONS["inputs"]["freq"][1],
                freq.replace("Hz", "").replace("kHz", "k")
            )
            results.append(f"freq={freq}")

        if gain is not None:
            await self.set_input_value(
                EQ_POSITIONS["inputs"]["gain"][0],
                EQ_POSITIONS["inputs"]["gain"][1],
                gain.replace("dB", "")
            )
            results.append(f"gain={gain}")

        if q is not None:
            await self.set_input_value(
                EQ_POSITIONS["inputs"]["res"][0],
                EQ_POSITIONS["inputs"]["res"][1],
                q
            )
            results.append(f"q={q}")

        return SkillResult(success=True, message=f"Band {band}: {', '.join(results)}")

    async def set_filter_type(self, band: int, filter_type: str) -> SkillResult:
        """Set the filter type for a band.

        Args:
            band: Band number 1-6
            filter_type: One of 'Bell/Peak', 'High-pass', 'Low-pass', 'High-shelf', 'Low-shelf', 'Notch'
        """
        if filter_type not in FILTER_TYPE_NAMES:
            return SkillResult(success=False, message=f"Unknown filter: {filter_type}. Available: {FILTER_TYPE_NAMES}")

        await self.select_band(band)
        await self.wait(0.3)

        idx = FILTER_TYPE_NAMES.index(filter_type)
        pos = EQ_POSITIONS["filter_types"][idx]
        await self.click_at(pos[0], pos[1])

        return SkillResult(success=True, message=f"Band {band} filter: {filter_type}")

    async def get_current_state(self) -> SkillResult:
        """Read the current EQ state (all bands)."""
        bands = {}
        for band_num in range(1, 7):
            await self.select_band(band_num)
            await self.wait(0.5)

            # Read the input values
            values = await self.browser.evaluate("""() => {
                const vw = window.innerWidth;
                const inputs = [];
                document.querySelectorAll('input').forEach(inp => {
                    const r = inp.getBoundingClientRect();
                    if (r.x > vw * 0.7 && r.y > 660 && r.y < 710 && r.width > 30) {
                        inputs.push({x: Math.round(r.x), value: inp.value});
                    }
                });
                return inputs.sort((a, b) => a.x - b.x);
            }""") or []

            if len(values) >= 3:
                bands[band_num] = {
                    "freq": values[0]["value"],
                    "gain": values[1]["value"],
                    "q": values[2]["value"],
                }
            else:
                bands[band_num] = {"freq": "?", "gain": "?", "q": "?"}

        return SkillResult(success=True, message="EQ state read", data=bands)

    async def _get_current_preset(self) -> Optional[str]:
        """Get the name of the currently selected preset."""
        result = await self.browser.evaluate("""() => {
            const vw = window.innerWidth;
            const buttons = document.querySelectorAll('button');
            for (const btn of buttons) {
                const r = btn.getBoundingClientRect();
                const text = btn.textContent.trim();
                if (r.x > vw * 0.7 && r.y > 330 && r.y < 400 && r.width > 80 && text.length > 2) {
                    return text;
                }
            }
            return null;
        }""")
        return result

    async def apply_custom_eq(self, settings: dict) -> SkillResult:
        """Apply a complete custom EQ configuration.

        Args:
            settings: Dict with band numbers as keys, each containing freq/gain/q/filter_type.
                Example: {
                    1: {"freq": "80Hz", "gain": "-3dB", "q": "0.7", "filter_type": "High-pass"},
                    3: {"freq": "500Hz", "gain": "2dB", "q": "1.2"},
                }
        """
        # Enable EQ first
        await self.enable()

        for band_num, params in settings.items():
            band = int(band_num)

            # Set filter type if specified
            if "filter_type" in params:
                await self.set_filter_type(band, params["filter_type"])

            # Set band parameters
            await self.set_band(
                band,
                freq=params.get("freq"),
                gain=params.get("gain"),
                q=params.get("q"),
            )

        return SkillResult(success=True, message=f"Applied custom EQ ({len(settings)} bands)")
