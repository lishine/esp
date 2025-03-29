# queue.py Statically allocated uasyncio queue
# Author: Peter Hinch
# Copyright Peter Hinch 2017-2020 Released under the MIT license

# Provides Queue class. See docs.

import uasyncio as asyncio

# from . import launch # Removed unused import

# V3 allows task cancellation
# Exception raised by get_nowait().


class QueueEmpty(Exception):
    pass


# Exception raised by put_nowait().


class QueueFull(Exception):
    pass


class Queue:
    def __init__(self, maxsize=0):
        self._maxsize = maxsize
        self._evput = asyncio.Event()  # Triggered by put, tested by get
        self._evget = asyncio.Event()  # Triggered by get, tested by put
        self._queue = []

    # These methods are for use by user code:

    def qsize(self):
        return len(self._queue)

    @property
    def maxsize(self):
        return self._maxsize

    def empty(self):
        return not self._queue

    def full(self):
        return self._maxsize > 0 and self.qsize() >= self._maxsize

    def get_nowait(self):  # Remove and return an item from the queue.
        # Return an item if one is immediately available, else raise QueueEmpty.
        if self.empty():
            raise QueueEmpty()
        res = self._queue.pop(0)
        self._evget.set()  # Schedule tasks waiting on put
        self._evget.clear()
        return res

    def put_nowait(self, val):  # Put an item into the queue without blocking.
        # If the queue is full, raise QueueFull.
        if self.full():
            raise QueueFull()
        self._queue.append(val)
        self._evput.set()  # Schedule tasks waiting on get
        self._evput.clear()

    async def get(self):  # Remove and return an item from the queue.
        # Wait for an item if queue is empty. Task cancellation will raise CancelledError.
        while self.empty():
            # Queue is empty, suspend task until a put occurs
            await self._evput.wait()
        res = self._queue.pop(0)
        self._evget.set()  # Schedule tasks waiting on put
        self._evget.clear()
        return res

    async def put(self, val):  # Put an item into the queue.
        # If the queue is full, wait for an item to be got. Task cancellation will raise CancelledError.
        while self.full():
            # Queue is full, suspend task until a get occurs
            await self._evget.wait()
        self._queue.append(val)
        self._evput.set()  # Schedule tasks waiting on get
        self._evput.clear()

    # Task cancellation support. This is relevant if the Queue is likely to
    # be acquired prior to cancellation. It sets the relevant event.
    def __iter__(self):  # Usage: yield from queue
        while True:
            yield self.get

    __next__ = __iter__

    def __aiter__(self):
        return self

    async def __anext__(self):
        return await self.get()
