"""WhatsApp webhook contracts.

The primary interface: no app to install, no data cost to search. Everything
a commuter can do goes through here, so this feature is a thin translator --
it turns messages into calls on the other features and turns their answers
back into text. No routing or fare logic belongs in this package.
"""

from enum import Enum

from pydantic import BaseModel, Field


class InboundMessage(BaseModel):
    """Normalised from the provider payload -- Twilio and the WhatsApp Business
    API disagree on field names, so neither shape is used past the router."""

    from_number: str = Field(..., description="E.164. Treat as personal data.")
    body: str
    message_id: str
    provider: str = Field("twilio", examples=["twilio", "meta"])


class ReplyKind(str, Enum):
    text = "text"
    quick_reply = "quick_reply"


class OutboundReply(BaseModel):
    to_number: str
    kind: ReplyKind = ReplyKind.text
    body: str
    options: list[str] = Field(default_factory=list,
                               description="Quick-reply buttons, e.g. confirming "
                                           "a fare in one tap.")


class WebhookAck(BaseModel):
    """What the provider gets back. Never the reply itself -- replies are sent
    out-of-band so a slow lookup cannot time out the webhook."""

    received: bool = True
