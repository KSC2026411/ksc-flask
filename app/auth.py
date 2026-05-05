from datetime import datetime, timedelta

def get_delay(attempts):
    if attempts == 3:
        return timedelta(seconds=30)
    elif attempts == 4:
        return timedelta(minutes=1)
    elif attempts >= 5:
        return timedelta(minutes=5)
    return timedelta(0)

def login(user, password):
    if datetime.now() < user.next_allowed_login:
        remaining = user.next_allowed_login - datetime.now()
        return False, f"Try again in {remaining.seconds} seconds"

    if check_password(password, user.password_hash):
        user.failed_attempts = 0
        user.next_allowed_login = datetime.min
        return True, "Login successful"

    user.failed_attempts += 1
    delay = get_delay(user.failed_attempts)
    user.next_allowed_login = datetime.now() + delay

    return False, f"Invalid credentials. Next attempt in {delay.seconds} seconds"