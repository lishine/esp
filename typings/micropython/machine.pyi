from typing import Optional, Union, Callable, Tuple, Any

class Pin:
    IN: int
    OUT: int
    PULL_UP: int
    PULL_DOWN: int
    IRQ_RISING: int
    IRQ_FALLING: int
    
    def __init__(self, id: Union[int, str], mode: int = -1, pull: int = -1, value: Optional[int] = None) -> None: ...
    def init(self, mode: int = -1, pull: int = -1, value: Optional[int] = None) -> None: ...
    def value(self, x: Optional[int] = None) -> Optional[int]: ...
    def on(self) -> None: ...
    def off(self) -> None: ...
    def irq(self, handler: Callable = None, trigger: int = IRQ_FALLING | IRQ_RISING, priority: int = 1) -> Any: ...

def reset() -> None: ...
def freq(hz: Optional[int] = None) -> int: ...
def unique_id() -> bytes: ...