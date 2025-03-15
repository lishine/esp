from collections import deque


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
    """Log function that stores messages in a circular buffer and prints to console"""
    output = " ".join(str(arg) for arg in args)
    log_buffer.append(output)
    print(*args, **kwargs)
