import math
from datetime import datetime
from datetime import timezone as timezone
from enum import Enum, auto

class StatusCode(Enum):
	OK = auto()
	ERROR = auto()

class ShouldPlaceOrderCode(Enum):
	YES = auto()
	NO = auto()
	TOO_SOON = auto()

# Return number of seconds between now and the next top-of-the-delay-period.
# Eg, if delay_period is 1m, and we are 45s away from the next minute, then
# only wait 45s; but if we are 15s away from the next minute, wait 75s so that
# any processing required in the current minute has sufficient time to complete.
def get_next_delay_period(delay_period):
	now = datetime.utcnow().replace(tzinfo=timezone.utc).timestamp()
	seconds = math.floor(now)
	seconds_into_delay_period = seconds % delay_period
	half_delay_period = (delay_period / 2.0)
	if seconds_into_delay_period < half_delay_period:
		# Wait less than one full delay period.
		delay_period -= seconds_into_delay_period
	else:
		# Wait more than one full delay period.
		delay_period += (delay_period - seconds_into_delay_period)
	return delay_period
