import logging
import time
from datetime import UTC, datetime
from functools import wraps
from threading import RLock
from typing import Any

import pint
import serial
import xarray as xr
from tomato.driverinterface_3_0 import (
    Attr,
    ModelComponent,
    ModelInterface,
    Settings,
    Status,
)
from tomato.driverinterface_3_0.decorators import coerce_val

READ_DELAY = 0.02
SERIAL_TIMEOUT = 0.2
READ_TIMEOUT = 2.0
logger = logging.getLogger(__name__)


def read_delay(func):
    @wraps(func)
    def wrapper(self: "Component", **kwargs):
        if time.perf_counter() - self.last_action < READ_DELAY:
            time.sleep(READ_DELAY)
        return func(self, **kwargs)

    return wrapper


class Settings(Settings):
    idle_measurement_interval: int = 10


class DriverInterface(ModelInterface):
    pass


class Component(ModelComponent):
    s: serial.Serial
    last_action: float
    constants: dict
    units: str

    @property
    @read_delay
    def pressure(self) -> pint.Quantity:
        ret = self._comm(b"P\r\n")
        val, unit, _ag = ret[0].split()
        qty = pint.Quantity(f"{val} {unit}")
        self.last_action = time.perf_counter()
        return qty

    def __init__(self, driver: ModelInterface, name: str, address: str, **kwargs: dict):
        super().__init__(driver, name, **kwargs)

        self.s = serial.Serial(
            port=address,
            baudrate=115200,
            bytesize=8,
            stopbits=1,
            timeout=SERIAL_TIMEOUT,
            exclusive=True,
        )

        self.last_action = time.perf_counter()
        self.constants = {}
        self.portlock = RLock()

        ret = self._comm(b"SNR\r\n")
        self.constants["serial"] = ret[0].split("=")[1].strip()

        ret = self._comm(b"ENQ\r\n")
        _minv, _to, _maxv, unit, ag = ret[2].split()
        self.units = unit
        self.constants["gauge"] = ag == "G"

    def attrs(self, **kwargs: dict) -> dict[str, Attr]:
        attrs_dict = {
            "pressure": Attr(type=pint.Quantity, units=self.units, status=True),
        }
        return attrs_dict

    def capabilities(self, **kwargs: dict) -> set:
        capabs = {"measure_pressure"}
        return capabs

    def do_measure(self, **kwargs: dict) -> None:
        coords = {"uts": (["uts"], [datetime.now(UTC).timestamp()])}
        qty = self.pressure
        data_vars = {
            "pressure": (["uts"], [qty.m], {"units": str(qty.u)}),
        }
        self.last_data = xr.Dataset(
            data_vars=data_vars,
            coords=coords,
        )

    def get_attr(self, attr: str, **kwargs: dict) -> pint.Quantity:
        if attr not in self.attrs():
            raise AttributeError(f"Unknown attr: {attr!r}")
        return getattr(self, attr)

    @coerce_val
    def set_attr(self, attr: str, val: Any, **kwargs: dict) -> None:
        pass

    def status(self, **kwargs: dict) -> Status:
        connected: bool = self.s.is_open
        if connected:
            attrs = {attr: self.get_attr(attr) for attr in self.attrs()}
            state = self.state
            task = self.running_task
        else:
            attrs = {}
            state = None
            task = None

        return Status(
            connected=connected,
            state=state,  # ty: ignore[invalid-argument-type]
            can_submit=connected,
            attrs=attrs,
            task=task,
        )

    def quit(self, **kwargs: dict) -> None:
        if self.s.is_open:
            logger.debug("%s: closing Socket", self.name)
            self.s.close()

    def _comm(self, command: bytes) -> list[str]:
        lines = []
        t0 = time.perf_counter()
        with self.portlock:
            logger.debug("%s", command.rstrip())
            self.s.write(command)
            # TODO: rewrite using read_until(sequence=b">")
            while time.perf_counter() - t0 < READ_TIMEOUT:
                lines += self.s.readlines()
                logger.debug("%s", lines)
                if b">" in lines:
                    break
                time.sleep(READ_DELAY)
            else:
                raise RuntimeError(f"Read took too long: {lines}")
        lines = [i.decode().strip() for i in lines[:-1]]
        return lines
