import random
import string

def generate_tracking(length=10):
    return "TRK" + ''.join(
        random.choices(string.ascii_uppercase + string.digits, k=length)
    )