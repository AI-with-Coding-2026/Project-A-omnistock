import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction

logger = logging.getLogger(__name__)


def _send_after_commit(subject, message, recipient_email):
    """
    Sends a plain-text email once the current transaction commits, so a
    notification failure or a console-backend hiccup never blocks or rolls
    back the PO/order state change itself.
    Silently (but loudly, via logging) skips sending if recipient_email is
    blank, rather than raising.
    """
    if not recipient_email:
        logger.warning(
            "Skipped sending email '%s' - no recipient email address available.",
            subject,
        )
        return

    def _send():
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient_email],
                fail_silently=False,
            )
        except Exception:
            logger.exception("Failed to send email '%s' to %s", subject, recipient_email)

    transaction.on_commit(_send)


def send_po_issued_notification(purchase_order):
    """Notifies the supplier that a new PO has been issued to them."""
    supplier = purchase_order.supplier
    subject = f"New Purchase Order {purchase_order.po_number}"
    message = (
        f"Hello {supplier.name},\n\n"
        f"A new purchase order {purchase_order.po_number} has been issued to you.\n"
        f"Please log in to the supplier portal to review and respond.\n\n"
        f"Thank you."
    )
    _send_after_commit(subject, message, supplier.email)


def send_po_response_notification(purchase_order, outcome):
    """
    Notifies the PO's creator that the supplier has accepted or rejected it.
    `outcome` should be 'accepted' or 'rejected'.
    """
    creator = purchase_order.created_by
    subject = f"Purchase Order {purchase_order.po_number} {outcome}"
    message = (
        f"Hello {creator.get_full_name() or creator.username},\n\n"
        f"Purchase order {purchase_order.po_number} has been {outcome} "
        f"by {purchase_order.supplier.name}.\n\n"
        f"Thank you."
    )
    _send_after_commit(subject, message, creator.email)