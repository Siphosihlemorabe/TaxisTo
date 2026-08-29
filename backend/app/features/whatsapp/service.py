"""Conversation handling.

SCAFFOLD -- see `features/routes/service.py` for the convention.
"""

from typing import Mapping

from .schemas import InboundMessage, OutboundReply


class WhatsAppService:
    def parse(self, form: Mapping[str, str]) -> InboundMessage:
        """Normalise a provider payload into `InboundMessage`.

        Twilio and the Meta Business API disagree on field names, so this is
        the only place either shape is understood.
        """
        raise NotImplementedError(
            "Payload parsing is not implemented. Needs: Twilio's From/Body/"
            "MessageSid form fields, and the Meta JSON equivalent."
        )

    def verify_signature(self, signature: str | None, url: str, payload: bytes) -> bool:
        """Confirm the request really came from the provider.

        Deliberately has no "skip if no token configured" branch. An unverified
        webhook is an open relay into the fare data, and a missing token is a
        deployment error, not a permission to accept anything.
        """
        raise NotImplementedError(
            "Signature verification is not implemented. Needs: Twilio's HMAC-SHA1 "
            "scheme over the full URL and sorted POST params, compared with "
            "hmac.compare_digest, using settings.twilio_auth_token."
        )

    def handle(self, message: InboundMessage) -> OutboundReply:
        """Turn one inbound message into one reply.

        Note for implementation: this needs conversation state (which question
        was asked last), which is the second piece of non-pipeline state in the
        system after fares. Keep it keyed by from_number with a short TTL.
        """
        raise NotImplementedError(
            "Message handling is not implemented. Needs: intent parsing, "
            "per-sender conversation state, and delegation to the routes, "
            "fares and pickup services."
        )

    def send(self, reply: OutboundReply) -> None:
        """Deliver out-of-band, after the webhook has already been acked."""
        raise NotImplementedError(
            "Outbound sending is not implemented. Needs: a provider client and "
            "credentials."
        )
