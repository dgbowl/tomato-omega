from typing import Any
from tomato.driverinterface_2_1 import ModelInterface, ModelDevice, Attr
from tomato.driverinterface_2_1.decorators import coerce_val
from tomato.driverinterface_2_1.types import Val
import serial
from datetime import datetime
import xarray as xr
import pint
import time
from functools import wraps

READ_DELAY = 0.01
SERIAL_TIMEOUT = 0.2
READ_TIMEOUT = 1.0


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
        self.s.write(b"P\r\n")
        ret = self._read()
        val, unit, ag = ret[0].split()
        return pint.Quantity(f"{val} {unit}")

    def __init__(self, driver: ModelInterface, key: tuple[str, str], **kwargs: dict):
        address, _ = key
        self.s = serial.Serial(
            port=address,
            baudrate=115200,
            bytesize=8,
            stopbits=1,
            timeout=SERIAL_TIMEOUT,
        )
        super().__init__(driver, key, **kwargs)

        self.last_action = time.perf_counter()
        self.constants = dict()

        self.s.write(b"SNR\r\n")
        ret = self._read()
        self.constants["serial"] = ret[0].split("=")[1].strip()

        self.s.write(b"ENQ\r\n")
        ret = self._read()
        minv, to, maxv, unit, ag = ret[2].split()
        self.units = unit
        self.constants["gauge"] = True if ag == "G" else False

    def attrs(self, **kwargs: dict) -> dict[str, Attr]:
        attrs_dict = {
            "pressure": Attr(type=pint.Quantity, units=self.units, status=True),
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

    def _read(self) -> list[str]:
        lines = []
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < READ_TIMEOUT:
            lines += self.s.readlines()
            if b">" in lines:
                break
            time.sleep(READ_DELAY)
        else:
            raise RuntimeError(f"Read took too long: {lines}")
        lines = [i.decode().strip() for i in lines[:-1]]
        return lines
