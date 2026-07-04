"""Operator approval line: a trusted human command channel.

DALEOBANKS contacts the operator only when judgment is required — emergency
approvals, freezes, news briefings, interview questions, and opinion intake.
Commands arrive by SMS (Twilio webhook) or the dashboard; both paths run
through :meth:`OperatorLine.handle_command`.

Command grammar (first word, case-insensitive; ``<id>`` is any unique prefix
of a request id and may be omitted when exactly one request is pending):

    YES [<id>]          approve exactly that request — never standing autonomy
    NO [<id>]           reject the request
    EDIT [<id>] <text>  approve with the operator's replacement text
    WHY [<id>]          explain why the agent is asking
    HOLD [<id>]         park the request for later (YES/NO still work on it)
    FREEZE              immediately disarm all outbound action (kill switch)
    NEWS                a short briefing of what the agent has been sensing
    INTERVIEW           the question the agent most wants answered right now
    OPINION: <thought>  store the thought as a self-signal, never doctrine

Every prompt and command is ledgered (``operator_prompted`` /
``operator_command``).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import urllib.parse
import urllib.request
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional

from db.models import ApprovalRequest, DiscoveryProposal, GoalProposal, SelfSignal, SensedEvent
from services.ledger import DecisionLedger, KillSwitch, get_kill_switch, get_ledger
from services.logging_utils import get_logger

logger = get_logger(__name__)

HELP_TEXT = (
    "Commands: YES [id], NO [id], EDIT [id] <text>, WHY [id], HOLD [id], "
    "FREEZE, NEWS, INTERVIEW, OPINION: <thought>"
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
        return all(
            os.getenv(var)
            for var in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM", "OPERATOR_PHONE")
        )

    def request_approval(
        self,
        session: Any,
        kind: str,
        summary: str,
        payload: Optional[Dict[str, Any]] = None,
        rationale: str = "",
    ) -> ApprovalRequest:
        """File an ApprovalRequest and prompt the operator (SMS if configured,
        dashboard inbox always)."""
        request = ApprovalRequest(
            kind=kind, summary=summary, payload=payload or {}, rationale=rationale
        )
        session.add(request)
        session.commit()

        short = request.id[:8]
        sms_sent = False
        if self.sms_configured:
            sms_sent = self._send_sms(
                f"[DaLeoBanks] {summary} — reply YES {short} / NO {short} / WHY {short}"
            )
        self.ledger.record("operator_prompted", {
            "id": request.id,
            "kind": kind,
            "summary": summary[:120],
            "sms_sent": sms_sent,
        })
        return request

    def _send_sms(self, body: str) -> bool:
        sid = os.getenv("TWILIO_ACCOUNT_SID", "")
        token = os.getenv("TWILIO_AUTH_TOKEN", "")
        try:
            data = urllib.parse.urlencode({
                "To": os.getenv("OPERATOR_PHONE", ""),
                "From": os.getenv("TWILIO_FROM", ""),
                "Body": body[:1500],
            }).encode()
            req = urllib.request.Request(
                f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                data=data,
                method="POST",
            )
            auth = base64.b64encode(f"{sid}:{token}".encode()).decode()
            req.add_header("Authorization", f"Basic {auth}")
            with urllib.request.urlopen(req, timeout=10) as resp:
                return 200 <= resp.status < 300
        except Exception as exc:
            logger.error(f"Operator SMS send failed: {exc}")
            return False

    # ------------------------------------------------------------------ #
    # Inbound: executing operator commands
    # ------------------------------------------------------------------ #
    def handle_command(self, session: Any, text: str, via: str = "dashboard") -> Dict[str, Any]:
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
        request, error = self._resolve(session, arg)
        if request is None:
            return self._done(cmd, via, ok=False, reply=error)

        status = {"YES": "approved", "NO": "rejected", "HOLD": "held"}[cmd]
        request.status = status
        request.decided_at = datetime.now(UTC)
        request.decided_via = via
        session.commit()
        reply = f"{status.capitalize()}: {request.summary}"
        if cmd == "YES":
            reply += " (this approval covers only this request)"
        return self._done(cmd, via, ok=True, reply=reply, request_id=request.id)

    def _edit(self, session: Any, rest: str, via: str) -> Dict[str, Any]:
        maybe_id, _, text = rest.partition(" ")
        request, _ = self._resolve(session, maybe_id) if maybe_id else (None, None)
        if request is None:
            # No id prefix given — the whole rest is the replacement text.
            request, error = self._resolve(session, "")
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
            reply=f"Edited and approved with your text: {request.summary}",
            request_id=request.id,
        )

    def _why(self, session: Any, arg: str, via: str) -> Dict[str, Any]:
        request, error = self._resolve(session, arg)
        if request is None:
            return self._done("WHY", via, ok=False, reply=error)
        reply = f"[{request.kind}] {request.summary}"
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

    def _resolve(self, session: Any, arg: str):
        """Find the request a command targets. Bare commands only work when
        exactly one request is pending — YES can never be ambiguous."""
        arg = (arg or "").strip().lower()
        candidates: List[ApprovalRequest] = (
            session.query(ApprovalRequest)
            .filter(lambda r: r.status in _DECIDABLE)
            .order_by(lambda r: r.created_at, descending=True)
            .all()
        )
        if arg:
            matches = [r for r in candidates if r.id.lower().startswith(arg)]
            if len(matches) == 1:
                return matches[0], None
            if not matches:
                return None, f"No open request matches '{arg}'."
            return None, f"'{arg}' is ambiguous ({len(matches)} matches) — use more characters."

        pending = [r for r in candidates if r.status == "pending"]
        if len(pending) == 1:
            return pending[0], None
        if not pending:
            return None, "No pending requests."
        ids = ", ".join(r.id[:8] for r in pending[:5])
        return None, f"{len(pending)} requests pending — specify one: {ids}"

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
            return f"Decide this first: {oldest.summary} (YES {oldest.id[:8]} / NO {oldest.id[:8]})"
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


def validate_twilio_signature(url: str, params: Dict[str, str], signature: str) -> bool:
    """Validate Twilio's X-Twilio-Signature header (HMAC-SHA1 over the URL
    plus sorted POST params, keyed by the auth token)."""
    token = os.getenv("TWILIO_AUTH_TOKEN", "")
    if not token or not signature:
        return False
    payload = url + "".join(key + params[key] for key in sorted(params))
    digest = hmac.new(token.encode(), payload.encode("utf-8"), hashlib.sha1).digest()
    expected = base64.b64encode(digest).decode()
    return hmac.compare_digest(expected, signature)


_SHARED_LINE: Optional[OperatorLine] = None


def get_operator_line() -> OperatorLine:
    global _SHARED_LINE
    if _SHARED_LINE is None:
        _SHARED_LINE = OperatorLine()
    return _SHARED_LINE


def set_operator_line(line: Optional[OperatorLine]) -> None:
    global _SHARED_LINE
    _SHARED_LINE = line
