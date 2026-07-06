
#estimates walking time between two park locations using the haversine formula, adjusted for the fact that park paths aren't straight lines.

import math

# average park-walking speed (slower than open-street pace)
WALK_SPEED_MPH = 2.8 
# some windiness since not all directions are straight lines
WINDINESS = 1.35  


def haversine_miles(lat1, lng1, lat2, lng2) -> float:
    R = 3958.8  # earth radius in miles
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))

#estimated walking time calculation
def walk_time_minutes(lat1, lng1, lat2, lng2) -> float:
    if None in (lat1, lng1, lat2, lng2):
        return 6.0

    straight_line = haversine_miles(lat1, lng1, lat2, lng2)
    actual_miles  = straight_line * WINDINESS
    return round((actual_miles / WALK_SPEED_MPH) * 60)
