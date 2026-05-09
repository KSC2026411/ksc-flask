import random
import string
import json

from pywebpush import webpush
from flask import current_app

from app.models import PushSubscription, User


# ==========================================
# TRACKING NUMBER GENERATOR (IMPROVED)
# ==========================================

def generate_tracking():
    """
    Generates short, readable, unique tracking number:
    Example: KSC-48291
    """

    return f"KSC-{random.randint(10000, 99999)}"


# ==========================================
# PUSH NOTIFICATIONS
# ==========================================

def send_push_notification(
    title,
    body,
    url="/",
    badge=1,
    role=None
):

    try:

        query = PushSubscription.query

        # Filter by role if specified
        if role:
            query = query.join(User).filter(User.role == role)

        subscriptions = query.all()

        print(f"📦 Sending push to {len(subscriptions)} users")

        for sub in subscriptions:

            try:

                webpush(

                    subscription_info=json.loads(sub.subscription),

                    data=json.dumps({
                        "title": title,
                        "body": body,
                        "url": url,
                        "badge": badge
                    }),

                    vapid_private_key=current_app.config["VAPID_PRIVATE_KEY"],

                    vapid_claims={
                        "sub": "mailto:admin@ksclogistics.com"
                    }

                )

                print(f"✅ Push sent to user {sub.user_id}")

            except Exception as e:
                print(f"❌ Push failed for user {sub.user_id}:", e)

    except Exception as e:
        print("❌ Global push error:", e)