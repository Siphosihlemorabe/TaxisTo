from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request

from .schemas import InboundMessage, WebhookAck
from .service import WhatsAppService

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])


def get_service() -> WhatsAppService:
    return WhatsAppService()


ServiceDep = Annotated[WhatsAppService, Depends(get_service)]


@router.post("/webhook", response_model=WebhookAck,
             summary="Inbound message from the messaging provider")
async def webhook(
    request: Request,
    service: ServiceDep,
    background: BackgroundTasks,
) -> WebhookAck:
    """Verify, ack immediately, then reply out-of-band.

    The provider retries on a slow response, so the lookup must not happen
    inside the request -- a duplicated retry would double-count a fare report.
    """
    body = await request.body()
    service.verify_signature(
        request.headers.get("X-Twilio-Signature"), str(request.url), body
    )
    message = service.parse(await request.form())
    background.add_task(lambda: service.send(service.handle(message)))
    return WebhookAck()
