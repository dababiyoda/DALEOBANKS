"""Operator approval line: a trusted human command channel.

DALEOBANKS contacts the operator only when judgment is required — emergency
approvals, freezes, news briefings, interview questions, and opinion intake.
Commands arrive by SMS (Twilio webhook) or the dashboard; both paths run
through :meth:`OperatorLine.handle_command`.

This module is the public facade: transport concerns (SMS sending, webhook
signature validation) live in ``services/operator_notifications.py``; the
briefing/interview/opinion logic is small enough to live here until it isn't.

Command grammar (first word, case-insensitive; ``<code>`` is the request's
4-character approval code, also accepted as a unique id prefix):

    YES <code>          approve exactly that request — never standing autonomy
                        (a bare YES works only when exactly one P1 request is
                        pending; otherwise it is rejected)
    NO [<code>]         reject the request
    EDIT [<code>] <text> approve with the operator's replacement text
    WHY [<code>]        explain why the agent is asking
    HOLD [<code>]       park the request for later (YES/NO still work on it)
    FREEZE              immediately disarm all outbound action (kill switch)
    NEWS                a short briefing of what the agent has been sensing
    INTERVIEW           the question the agent most wants answered right now
    OPINION: <thought>  store the thought as a self-signal, never doctrine

Every prompt and command is ledgered (``operator_prompted`` /
``operator_command``).
"""

from __future__ import annotations

from datetime import datetime, UTC
from typing import Any, Dict, List, Optional, Tuple

from db.models import ApprovalRequest, DiscoveryProposal, GoalProposal, SelfSignal, SensedEvent
from services import operator_notifications as notifications
from services.ledger import DecisionLedger, KillSwitch, get_kill_switch, get_ledger
from services.logging_utils import get_logger
from services.operator_notifications import validate_twilio_signature  # re-export

logger = get_logger(__name__)

HELP_TEXT = (
    "Commands: YES <code>, NO [code], EDIT [code] <text>, WHY [code], "
    "HOLD [code], FREEZE, NEWS, INTERVIEW, OPINION: <thought>"
)

_DECIDABLE = ("pending", "held")


class OperatorLine:
    """Sends approval prompts to the operator and executes their commands."""

    def __init__(
        self,
        ledger: Optional[DecisionLedger] = None,
        kill_switch: Optional[KillSwitch] = None,
    ) -> None:
        self._ledger = ledger
        self._kill_switch = kill_switch

    @property
    def ledger(self) -> DecisionLedger:
        return self._ledger or get_ledger()

    @property
    def kill_switch(self) -> KillSwitch:
        return self._kill_switch or get_kill_switch()

    # ------------------------------------------------------------------ #
    # Outbound: asking for judgment
    # ------------------------------------------------------------------ #
    @property
    def sms_configured(self) -> bool:
        return notifications.sms_configured()

    def request_approval(
        self,
        session: Any,
        kind: str,
        summary: str,
        payload: Optional[Dict[str, Any]] = None,
        rationale: str = "",
        priority: str = "P2",
        strongest_objection: str = "",
        ttl_hours: Optional[int] = None,
    ) -> ApprovalRequest:
        """File an ApprovalRequest and prompt the operator (SMS if configured,
        dashboard inbox always). Duplicate pending requests (same kind and
        payload) collapse into the existing one — the queue must never
        manufacture approval demand. Requests expire; silence is never
        consent, and an expired request simply closes."""
        payload = payload or {}
        if payload:  # only a non-empty payload identifies the same act
            for existing in session.query(ApprovalRequest).all():
                if (existing.status == "pending" and existing.kind == kind
                        and existing.payload == payload):
                    return existing

        import os as _os
        from datetime import timedelta as _td
        try:
            ttl = int(ttl_hours if ttl_hours is not None
                      else _os.getenv("APPROVAL_TTL_HOURS", "72"))
        except ValueError:
            ttl = 72
        request = ApprovalRequest(
            kind=kind, summary=summary, payload=payload,
            rationale=rationale, priority=priority,
            strongest_objection=strongest_objection,
            expires_at=datetime.now(UTC) + _td(hours=ttl),
        )
        session.add(request)
        session.commit()

        sms_sent = False
        if self.sms_configured:
            sms_sent = notifications.send_sms(
                f"[DaLeoBanks {request.code}/{priority}] {summary} — reply "
                f"YES {request.code} / NO {request.code} / WHY {request.code}"
            )
        self.ledger.record("operator_prompted", {
            "id": request.id,
            "code": request.code,
            "kind": kind,
            "priority": priority,
            "summary": summary[:120],
            "sms_sent": sms_sent,
        })
        return request

    def sweep_expired(self, session: Any) -> int:
        """Close pending requests past their expiry. Queue overflow and
        operator silence must never become implicit approval — an expired
        request is simply closed, ledgered, and gone."""
        expired = 0
        now = datetime.now(UTC)
        for request in session.query(ApprovalRequest).all():
            if (request.status == "pending" and request.expires_at
                    and now >= request.expires_at):
                request.status = "expired"
                request.decided_at = now
                request.decided_via = "expiry"
                expired += 1
                self.ledger.record("approval_expired", {
                    "id": request.id, "code": request.code, "kind": request.kind,
                })
        if expired:
            session.commit()
        return expired

    # ------------------------------------------------------------------ #
    # Inbound: executing operator commands
    # ------------------------------------------------------------------ #
    def handle_command(self, session: Any, text: str, via: str = "dashboard") -> Dict[str, Any]:
        self.sweep_expired(session)
        raw = (text or "").strip()
        if not raw:
            return self._done("HELP", via, ok=False, reply=HELP_TEXT)

        head, _, rest = raw.partition(" ")
        cmd = head.upper().rstrip(":")
        rest = rest.strip()

        if cmd in ("YES", "NO", "HOLD"):
            return self._decide(session, cmd, rest, via)
        if cmd == "EDIT":
            return self._edit(session, rest, via)
        if cmd == "WHY":
            return self._why(session, rest, via)
        if cmd == "FREEZE":
            self.kill_switch.set_armed(False, reason="operator_freeze")
            return self._done(cmd, via, ok=True, reply="Frozen. All outbound action is disarmed.")
        if cmd == "NEWS":
            return self._done(cmd, via, ok=True, reply=self._news_briefing(session))
        if cmd == "INTERVIEW":
            return self._done(cmd, via, ok=True, reply=self._interview_question(session))
        if cmd == "OPINION":
            return self._opinion(session, rest, via)
        return self._done(cmd, via, ok=False, reply=f"Unknown command. {HELP_TEXT}")

    def _decide(self, session: Any, cmd: str, arg: str, via: str) -> Dict[str, Any]:
        request, error = self._resolve(session, arg, command=cmd)
        if request is None:
            return self._done(cmd, via, ok=False, reply=error)

        status = {"YES": "approved", "NO": "rejected", "HOLD": "held"}[cmd]
        request.status = status
        request.decided_at = datetime.now(UTC)
        request.decided_via = via
        session.commit()
        reply = f"{status.capitalize()} [{request.code}]: {request.summary}"
        if cmd == "YES":
            reply += " (this approval covers only this request)"
        return self._done(cmd, via, ok=True, reply=reply, request_id=request.id)

    def _edit(self, session: Any, rest: str, via: str) -> Dict[str, Any]:
        maybe_code, _, text = rest.partition(" ")
        request, _ = self._resolve(session, maybe_code, command="EDIT") if maybe_code else (None, None)
        if request is None:
            # No code given — the whole rest is the replacement text.
            request, error = self._resolve(session, "", command="EDIT")
            text = rest
            if request is None:
                return self._done("EDIT", via, ok=False, reply=error)
        text = text.strip()
        if not text:
            return self._done("EDIT", via, ok=False, reply="EDIT needs replacement text.")

        request.payload["operator_edit"] = text
        request.status = "edited"
        request.decided_at = datetime.now(UTC)
        request.decided_via = via
        session.commit()
        return self._done(
            "EDIT", via, ok=True,
            reply=f"Edited and approved with your text [{request.code}]: {request.summary}",
            request_id=request.id,
        )

    def _why(self, session: Any, arg: str, via: str) -> Dict[str, Any]:
        request, error = self._resolve(session, arg, command="WHY")
        if request is None:
            return self._done("WHY", via, ok=False, reply=error)
        reply = f"[{request.code}/{request.priority} {request.kind}] {request.summary}"
        if request.rationale:
            reply += f" — because: {request.rationale}"
        content = request.payload.get("content")
        if content:
            reply += f' — draft: "{str(content)[:200]}"'
        return self._done("WHY", via, ok=True, reply=reply, request_id=request.id)

    def _opinion(self, session: Any, thought: str, via: str) -> Dict[str, Any]:
        thought = thought.strip()
        if not thought:
            return self._done("OPINION", via, ok=False, reply="OPINION needs a thought after the colon.")
        signal = SelfSignal(text=thought, source="operator_opinion")
        session.add(signal)
        session.commit()
        return self._done(
            "OPINION", via, ok=True,
            reply="Recorded as a self-signal. I will weigh it, not obey it.",
            extra={"self_signal_id": signal.id},
        )

    def _resolve(
        self, session: Any, arg: str, command: str = "YES"
    ) -> Tuple[Optional[ApprovalRequest], Optional[str]]:
        """Find the request a command targets.

        With an argument, match the approval code exactly or a unique id
        prefix. Bare YES is honored only when exactly one P1 request is
        pending — everything else must name its code, so the wrong action
        can never be approved by accident. Bare NO/HOLD/WHY/EDIT work when
        exactly one request is pending (rejecting or querying the only
        request is not a spoofable act)."""
        arg = (arg or "").strip().lower()
        candidates: List[ApprovalRequest] = (
            session.query(ApprovalRequest)
            .filter(lambda r: r.status in _DECIDABLE)
            .order_by(lambda r: r.created_at, descending=True)
            .all()
        )
        if arg:
            matches = [
                r for r in candidates
                if r.code.lower() == arg or r.id.lower().startswith(arg)
            ]
            if len(matches) == 1:
                return matches[0], None
            if not matches:
                return None, f"No open request matches '{arg.upper()}'."
            return None, f"'{arg.upper()}' is ambiguous ({len(matches)} matches)."

        pending = [r for r in candidates if r.status == "pending"]
        if not pending:
            return None, "No pending requests."
        if len(pending) > 1:
            codes = ", ".join(f"{r.code}({r.priority})" for r in pending[:5])
            return None, f"{len(pending)} requests pending — name one: {codes}"

        only = pending[0]
        if command == "YES" and only.priority != "P1":
            return None, (
                f"Include the code to approve: YES {only.code} "
                f"({only.priority} requests always need their code)"
            )
        return only, None

    # ------------------------------------------------------------------ #
    # Briefings
    # ------------------------------------------------------------------ #
    def _news_briefing(self, session: Any) -> str:
        events = (
            session.query(SensedEvent)
            .order_by(lambda e: e.created_at, descending=True)
            .limit(3)
            .all()
        )
        pending = session.query(ApprovalRequest).filter(lambda r: r.status == "pending").all()
        lines = []
        for event in events:
            snippet = str(event.payload.get("text") or event.payload.get("query") or "")[:80]
            lines.append(f"- {event.kind} via {event.source}: {snippet}".rstrip(": "))
        if not lines:
            lines.append("- Nothing sensed recently.")
        lines.append(f"Pending approvals: {len(pending)}.")
        from config import get_config
        lines.append(f"Live mode: {'ARMED' if get_config().LIVE else 'disarmed'}.")
        return "\n".join(lines)

    def _interview_question(self, session: Any) -> str:
        oldest = (
            session.query(ApprovalRequest)
            .filter(lambda r: r.status == "pending")
            .order_by(lambda r: r.created_at)
            .first()
        )
        if oldest:
            return (
                f"Decide this first: {oldest.summary} "
                f"(YES {oldest.code} / NO {oldest.code})"
            )
        discoveries = session.query(DiscoveryProposal).filter(lambda p: p.status == "pending").all()
        goals = session.query(GoalProposal).filter(lambda p: p.status == "pending").all()
        if discoveries or goals:
            return (
                f"{len(discoveries)} discovery and {len(goals)} goal proposals await review "
                "on the /approvals page. Which should I prioritize arguing for?"
            )
        return "What outcome would make the next 30 days a clear win for you?"

    def _done(
        self,
        command: str,
        via: str,
        ok: bool,
        reply: str,
        request_id: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        record: Dict[str, Any] = {"command": command, "via": via, "ok": ok}
        if request_id:
            record["request_id"] = request_id
        if extra:
            record.update(extra)
        try:
            self.ledger.record("operator_command", record)
        except Exception as exc:
            logger.error(f"Failed to ledger operator command: {exc}")
        result = {"ok": ok, "reply": reply}
        if request_id:
            result["request_id"] = request_id
        return result


_SHARED_LINE: Optional[OperatorLine] = None


def get_operator_line() -> OperatorLine:
    global _SHARED_LINE
    if _SHARED_LINE is None:
        _SHARED_LINE = OperatorLine()
    return _SHARED_LINE


def set_operator_line(line: Optional[OperatorLine]) -> None:
    global _SHARED_LINE
    _SHARED_LINE = line


__all__ = [
    "OperatorLine", "get_operator_line", "set_operator_line",
    "validate_twilio_signature", "HELP_TEXT",
]
