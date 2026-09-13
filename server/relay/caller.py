"""The simulated person on the other end of the line.

Real telephony is a Twilio media stream away, but none of the hard problems live
there. The hard problem is generating a good reply suggestion for a stranger's
question in under a second, with a pause on the line that is growing. That is
fully exercised here, for free, and deterministically enough to rehearse a demo.
"""

from __future__ import annotations

from .config import settings
from .prompts import build_partner_system_prompt, build_partner_user_prompt
from .providers import load_model
from .scenarios import find_scenario
from .schemas import CallReplyRequest, CallReplyResponse, PartnerReply
from .scripted import scripted_partner_reply


async def partner_reply(req: CallReplyRequest) -> CallReplyResponse:
    scenario = find_scenario(req.scenario_id)
    if scenario is None:
        return CallReplyResponse(text="Sorry, wrong number.", ended=True, source="scripted")

    # The opening line is fixed so every demo starts the same way.
    if not req.transcript:
        return CallReplyResponse(
            text=scenario.opening, ended=False, source=settings.provider  # type: ignore[arg-type]
        )

    model = load_model("fast")
    if model is None:
        text, ended = scripted_partner_reply(req.scenario_id, req.transcript)
        return CallReplyResponse(text=text, ended=ended, source="scripted")

    try:
        from strands import Agent

        agent = Agent(
            model=model,
            system_prompt=build_partner_system_prompt(scenario),
            tools=[],
            callback_handler=None,
        )
        result = await agent.invoke_async(
            build_partner_user_prompt(req.transcript),
            structured_output_model=PartnerReply,
        )
        reply = result.structured_output
        if reply is None or not reply.text.strip():
            raise ValueError("empty partner reply")

        return CallReplyResponse(
            text=reply.text.strip(),
            ended=reply.ended,
            source=settings.provider,  # type: ignore[arg-type]
        )
    except Exception as exc:
        print(f"[relay] partner reply fell back to scripted: {exc}")
        text, ended = scripted_partner_reply(req.scenario_id, req.transcript)
        return CallReplyResponse(text=text, ended=ended, source="scripted")
