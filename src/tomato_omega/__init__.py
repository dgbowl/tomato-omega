from datetime import datetime
from functools import wraps
from threading import RLock
from tomato.driverinterface_2_1 import ModelInterface, ModelDevice, Attr
from tomato.driverinterface_2_1.decorators import coerce_val
from tomato.driverinterface_2_1.types import Val
from typing import Any
import logging
import pint
import serial
import time
import xarray as xr


READ_RETRIES = 10
READ_DELAY = 0.05
SERIAL_TIMEOUT = 0.2
READ_TIMEOUT = 1.0
logger = logging.getLogger()


def read_delay(func):
    @wraps(func)
    def wrapper(self: ModelDevice, **kwargs):
        if time.perf_counter() - self.last_action < READ_DELAY:
            time.sleep(READ_DELAY)
        return func(self, **kwargs)

    return wrapper


class DriverInterface(ModelInterface):
    idle_measurement_interval = 10

    def DeviceFactory(self, key, **kwargs):
        return Device(self, key, **kwargs)


class Device(ModelDevice):
    s: serial.Serial
    last_action: float
    constants: dict
    units: str

    @property
    @read_delay
    def pressure(self) -> pint.Quantity:
        ret = self._comm(b"P\r\n")
        val, unit, ag = ret[0].split()
        qty = pint.Quantity(f"{val} {unit}")
        self.last_action = time.perf_counter()
        return qty

        for retry in range(READ_RETRIES):
            try:
                with self.portlock:
                    logger.debug("P\r\n")
                    self.s.write(b"P\r\n")
                    ret = self._read()
                val, unit, ag = ret[0].split()
                qty = pint.Quantity(f"{val} {unit}")
                break
            except pint.UndefinedUnitError:
                continue
        else:
            raise ValueError(f"Could not read pressure in {READ_RETRIES} attempts.")
        self.last_action = time.perf_counter()
        return qty

    def __init__(self, driver: ModelInterface, key: tuple[str, str], **kwargs: dict):
        address, _ = key
        self.s = serial.Serial(
            port=address,
            baudrate=115200,
            bytesize=8,
            stopbits=1,
            timeout=SERIAL_TIMEOUT,
            exclusive=True,
        )
        super().__init__(driver, key, **kwargs)

        self.last_action = time.perf_counter()
        self.constants = dict()
        self.portlock = RLock()

        ret = self._comm(b"SNR\r\n")
        self.constants["serial"] = ret[0].split("=")[1].strip()

        ret = self._comm(b"ENQ\r\n")
        minv, to, maxv, unit, ag = ret[2].split()
        self.units = unit
        self.constants["gauge"] = True if ag == "G" else False

    def attrs(self, **kwargs: dict) -> dict[str, Attr]:
        attrs_dict = {
            "pressure": Attr(type=pint.Quantity, units=self.units, status=False),
        }
        return attrs_dict

    def capabilities(self, **kwargs: dict) -> set:
        capabs = {"measure_pressure"}
        return capabs

    def do_measure(self, **kwargs: dict) -> None:
        coords = {"uts": (["uts"], [datetime.now().timestamp()])}
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
    def set_attr(self, attr: str, val: Any, **kwargs: dict) -> Val:
        pass

    def _comm(self, command: bytes) -> list[str]:
        lines = []
        t0 = time.perf_counter()
        with self.portlock:
            logger.debug(f"{command.rstrip()}")
            self.s.write(command)
            while time.perf_counter() - t0 < READ_TIMEOUT:
                lines += self.s.readlines()
                logger.debug(f"{lines=}")
                if b">" in lines:
                    break
                time.sleep(READ_DELAY)
            else:
                raise RuntimeError(f"Read took too long: {lines}")
        lines = [i.decode().strip() for i in lines[:-1]]
        return lines
