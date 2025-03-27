import utime

# Month abbreviations
_MONTH_ABBR = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


class CircularBuffer:
    def __init__(self, maxlen=1000):
        self.maxlen = maxlen
        self.buffer = []
        self.current = 0

    def append(self, item):
        if len(self.buffer) < self.maxlen:
            self.buffer.append(item)
        else:
            self.buffer[self.current] = item
            self.current = (self.current + 1) % self.maxlen

    def get_all(self):
        if len(self.buffer) < self.maxlen:
            return self.buffer
        return self.buffer[self.current :] + self.buffer[: self.current]


log_buffer = CircularBuffer(maxlen=100)


def log(*args, **kwargs):
    """Log function that stores messages in a circular buffer and prints to console with timestamp"""
    # Get current time
    now = utime.localtime()
    ms = utime.ticks_ms() % 1000

    # Format timestamp: DD-Mon-YYYY HH:MM:SS.ms
    timestamp = "{:02d}-{}-{:04d} {:02d}:{:02d}:{:02d}.{:03d}".format(
        now[2], _MONTH_ABBR[now[1] - 1], now[0], now[3], now[4], now[5], ms
    )

    # Original message
    message = " ".join(str(arg) for arg in args)

    # Prepend timestamp to message for buffer and print
    output = f"{timestamp} {message}"
    log_buffer.append(output)
    print(output, **kwargs)  # Print the combined output
