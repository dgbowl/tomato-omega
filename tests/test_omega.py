from tomato_omega import DriverInterface, Device
import time

if __name__ == "__main__":

    kwargs = dict(address="/dev/ttyUSB0", channel="0")
    device = Device(driver="omega", key=(kwargs["address"], kwargs["channel"]))
    print(f"{device=}")
    print(f"{device.constants=}")
    print(f"{device.units=}")
    print(f"{device.pressure=}")
    print(f"{device.get_attr(attr='pressure')=}")

    interface = DriverInterface()
    print(f"{interface=}")
    print(f"{interface.cmp_register(**kwargs)=}")
    print(f"{interface.cmp_get_attr(**kwargs, attr='pressure')=}")
    print(f"{interface.cmp_measure(**kwargs)=}")
    print(f"{interface.cmp_constants(**kwargs)=}")
    time.sleep(1)
    print(f"{interface.cmp_last_data(**kwargs)=}")

