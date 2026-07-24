from datetime import datetime, timezone
from datetime import time as time_type

DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def is_restaurant_open(restaurant) -> bool:
    now = datetime.now(timezone.utc)
    day_key = DAY_KEYS[now.weekday()]
    hours = restaurant.opening_hours.get(day_key)
    if not hours:
        return False
    open_time = time_type.fromisoformat(hours[0])
    close_time = time_type.fromisoformat(hours[1])
    current_time = now.time().replace(tzinfo=None)
    return open_time <= current_time < close_time
