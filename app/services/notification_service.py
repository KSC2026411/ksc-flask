import json
import os
from flask import current_app
from pywebpush import webpush, WebPushException
from ..extensions import db
from ..models import PushSubscription
def _get_vapid_private_key():
    private_key = current_app.config.get("VAPID_PRIVATE_KEY") or os.getenv("VAPID_PRIVATE_KEY")
    if not private_key:
        raise RuntimeError("VAPID_PRIVATE_KEY is not configured.")
    return private_key
def _get_vapid_subject():
    subject = current_app.config.get("VAPID_SUBJECT") or os.getenv("VAPID_SUBJECT")
    if not subject:
        raise RuntimeError("VAPID_SUBJECT is not configured.")
    return subject
def send_push_notification(subscription, title, message, url="/"):
    try:
        subscription_info = json.loads(subscription.subscription)
        payload = {
            "title": title,
            "message": message,
            "url": url
        }
        webpush(
            subscription_info=subscription_info,
            data=json.dumps(payload),
            vapid_private_key=_get_vapid_private_key(),
            vapid_claims={
                "sub": _get_vapid_subject()
            }
        )
        return True
    except WebPushException as exc:
        status_code = None
        try:
            if exc.response is not None:
                status_code = exc.response.status_code
        except Exception:
            pass
        print("❌ WEB PUSH ERROR:", status_code, str(exc))
        if status_code in (404, 410):
            try:
                db.session.delete(subscription)
                db.session.commit()
                print("🧹 Removed expired push subscription:", subscription.id)
            except Exception as cleanup_error:
                db.session.rollback()
                print("❌ FAILED TO REMOVE EXPIRED SUBSCRIPTION:", cleanup_error)
        return False
    except Exception as exc:
        print("❌ PUSH NOTIFICATION ERROR:", str(exc))
        return False
def notify_user(user_id, title, message, url="/"):
    subscriptions = PushSubscription.query.filter_by(user_id=user_id).all()
    if not subscriptions:
        print(f"ℹ️ No push subscriptions found for user {user_id}")
        return 0
    sent_count = 0
    for subscription in subscriptions:
        if send_push_notification(subscription, title, message, url):
            sent_count += 1
    return sent_count
def notify_users(user_ids, title, message, url="/"):
    sent_count = 0
    for user_id in user_ids:
        sent_count += notify_user(user_id, title, message, url)
    return sent_count
def notify_admins(title, message, url="/"):
    from ..models import User
    admins = User.query.filter_by(role="admin", is_active=True).all()
    sent_count = 0
    for admin in admins:
        sent_count += notify_user(admin.id, title, message, url)
    return sent_count
def notify_all_customers(title, message, url="/"):
    from ..models import User
    customers = User.query.filter_by(role="customer", is_active=True).all()
    sent_count = 0
    for customer in customers:
        sent_count += notify_user(customer.id, title, message, url)
    return sent_count