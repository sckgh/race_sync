"""Operator Console (component C8, specs/03 §3.2, specs/09 §9.9).

The human control surface for live running: trigger/clear Code 60, fire the timed chequer,
apply penalties, watch sync health, and override on failure. One operator, one screen.

The console is split into **logic** (this module) and presentation (the ``render`` method
returns a string; the CLI prints it / loops on input). That split keeps the command
handling and the dashboard view-model fully unit-testable without a TTY.

Design rules honoured (specs/09 §9.9): big obvious controls, **guarded destructive
actions** (the engine already guards illegal transitions; the console surfaces clear
errors instead of crashing), current state always visible, and Code 60 also pushed to the
injection adapter so the virtual field is neutralised in-world.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Optional

from .health import HealthMonitor, Status
from .injection.base import GlobalSimState, SimInjectionAdapter
from .model import RaceState
from .scoring import CarClass, ScoringService, format_classification
from .state_engine import InvalidTransition, RaceStateEngine

RACE_LAPS = 77  # Sydney 300 distance (specs/02); display only


@dataclass
class CommandResult:
    """Outcome of dispatching one operator command.

    Attributes:
        ok: Whether the command succeeded.
        message: Human-readable result or error message.
    """

    ok: bool
    message: str


HELP = """commands:
  arm                     PRE-RACE -> FORMATION (form up the virtual field)
  green                   release the field / restart after Code 60
  code60 on|off           deploy/withdraw Safety Car -> virtual Code 60
  chequer                 fire the timed chequer (needs the finish armed)
  chequer force           override: fire the chequer regardless
  penalty <car> <laps> [reason]   apply a lap penalty (e.g. penalty V2 1 code60)
  status                  redraw the dashboard
  help                    show this help
  quit                    exit the console"""


class OperatorConsole:
    """Operator control surface: command handling plus a dashboard view-model.

    Attributes:
        engine: Race-state engine driven by operator commands.
        health: Health monitor surfaced on the dashboard.
        scoring: Scoring service queried for classifications and penalties.
        adapter: Optional sim injection adapter pushed global state (e.g. Code 60).
        last_message: The most recent command result message shown on the dashboard.
    """

    def __init__(self, engine: RaceStateEngine, health: HealthMonitor,
                 scoring: ScoringService, adapter: Optional[SimInjectionAdapter] = None,
                 clock=None):
        self.engine = engine
        self.health = health
        self.scoring = scoring
        self.adapter = adapter
        self._clock = clock
        self.last_message = ""

    def _now(self, t: Optional[float] = None) -> float:
        if t is not None:
            return t
        if self._clock is not None:
            return self._clock()
        # Fall back to the latest time the state engine knows about.
        return self.engine.chequered_t or self.engine.finish_t or self.engine.green_t or 0.0

    # -- command handling --------------------------------------------------- #

    def dispatch(self, line: str, t: Optional[float] = None) -> CommandResult:
        """Parse and execute one operator command.

        Never raises on bad input; failures are returned as a non-ok result.

        Args:
            line: The raw command line entered by the operator.
            t: Optional explicit logical time; falls back to the clock or engine time.

        Returns:
            The command result.
        """
        try:
            parts = shlex.split(line.strip())
        except ValueError as exc:
            return CommandResult(False, f"parse error: {exc}")
        if not parts:
            return CommandResult(True, "")
        cmd, *args = parts
        cmd = cmd.lower()
        now = self._now(t)
        try:
            return self._run(cmd, args, now)
        except InvalidTransition as exc:
            return self._fail(f"not allowed: {exc}")
        except Exception as exc:  # noqa: BLE001 - console must stay alive
            return self._fail(f"error: {exc}")

    def _run(self, cmd: str, args: list[str], now: float) -> CommandResult:
        if cmd in ("help", "?"):
            return CommandResult(True, HELP)
        if cmd in ("status", ""):
            return CommandResult(True, "")
        if cmd in ("quit", "exit"):
            return CommandResult(True, "bye")
        if cmd == "arm":
            self.engine.arm(t=now)
            return self._ok("formation armed — virtual field forming up")
        if cmd == "green":
            self.engine.go_green(t=now)
            return self._ok("GREEN — field released")
        if cmd == "code60":
            return self._code60(args, now)
        if cmd == "chequer":
            return self._chequer(args, now)
        if cmd == "penalty":
            return self._penalty(args)
        return self._fail(f"unknown command: {cmd!r} (try 'help')")

    def _code60(self, args, now) -> CommandResult:
        if not args or args[0].lower() not in ("on", "off"):
            return self._fail("usage: code60 on|off")
        on = args[0].lower() == "on"
        self.engine.set_code60(on, t=now)
        if self.adapter is not None:
            self.adapter.set_global_state(GlobalSimState(code60=on))
        return self._ok("CODE 60 deployed — virtual field neutralised" if on
                        else "GREEN — Code 60 withdrawn, racing resumes")

    def _chequer(self, args, now) -> CommandResult:
        force = bool(args) and args[0].lower() in ("force", "!", "override")
        self.engine.fire_chequer(t=now, force=force)
        self.scoring.finalize(t=now)
        if self.adapter is not None:
            self.adapter.set_global_state(GlobalSimState(chequered=True))
        return self._ok("CHEQUERED FLAG — timed finish, results frozen"
                        + (" (forced)" if force else ""))

    def _penalty(self, args) -> CommandResult:
        if len(args) < 2:
            return self._fail("usage: penalty <car> <laps> [reason]")
        car, laps = args[0], args[1]
        try:
            n = int(laps)
        except ValueError:
            return self._fail(f"laps must be an integer, got {laps!r}")
        reason = " ".join(args[2:]) if len(args) > 2 else "operator penalty"
        if car not in {e.car_id for e in self.scoring.entries()}:
            return self._fail(f"unknown car {car!r}")
        self.scoring.add_penalty(car, laps=n, reason=reason)
        return self._ok(f"penalty: {car} +{n} lap(s) — {reason}")

    def _ok(self, msg: str) -> CommandResult:
        self.last_message = msg
        return CommandResult(True, msg)

    def _fail(self, msg: str) -> CommandResult:
        self.last_message = msg
        return CommandResult(False, msg)

    # -- rendering ---------------------------------------------------------- #

    def render(self, t: Optional[float] = None) -> str:
        now = self._now(t)
        snap = self.health.snapshot(now)
        st = self.engine.state
        banner = self._banner(st)
        leader = f"{self.engine.leader_car or '-'} (lap {self.engine.leader_lap}/{RACE_LAPS})"

        lines = [
            "+" + "-" * 64 + "+",
            f"| RaceSync OPERATOR CONSOLE      t={now:8.1f}s   {banner:<22}|",
            "+" + "-" * 64 + "+",
            f"  leader: {leader:<28} neutralised: {self.engine.neutralised_seconds():.0f}s",
            f"  health: {self._health_line(snap)}",
        ]
        if snap.alarms:
            for a in snap.alarms:
                lines.append(f"    ! {a}")
        lines.append("")
        for klass in (CarClass.REAL, CarClass.VIRTUAL):
            lines.append(format_classification(self.scoring.classify(klass, now)))
            lines.append("")
        if self.last_message:
            lines.append(f"  > {self.last_message}")
        lines.append("  (type 'help' for commands)")
        return "\n".join(lines)

    def _banner(self, st: RaceState) -> str:
        return {
            RaceState.PRE_RACE: "PRE-RACE",
            RaceState.FORMATION: "FORMATION LAP",
            RaceState.GREEN: "GREEN — RACING",
            RaceState.NEUTRALISED: "*** CODE 60 ***",
            RaceState.CHEQUERED: "CHEQUERED — FINISHED",
        }[st]

    def _health_line(self, snap) -> str:
        tag = {Status.GO: "GO", Status.DEGRADED: "DEGRADED", Status.FAULT: "FAULT"}[snap.overall]
        srcs = "  ".join(f"{name}:{sh.status.value}({sh.rate_hz:.0f}Hz)"
                         for name, sh in snap.sources.items())
        return f"{tag}   {srcs}" if srcs else tag

    # -- interactive loop --------------------------------------------------- #

    def run(self, input_fn=input, output_fn=print) -> None:
        """Run a simple REPL: render, read a command, act, repeat until quit.

        Args:
            input_fn: Callable that prompts for and returns a line of input.
            output_fn: Callable that writes a line of output.
        """
        output_fn(self.render())
        while True:
            try:
                line = input_fn("racesync> ")
            except (EOFError, KeyboardInterrupt):
                output_fn("\nbye")
                return
            res = self.dispatch(line)
            if line.strip().lower() in ("quit", "exit"):
                output_fn(res.message)
                return
            output_fn(self.render())
            if not res.ok:
                output_fn(f"  ! {res.message}")
