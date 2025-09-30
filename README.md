# tomato-omega
`tomato` driver for Omega *USBH pressure transducers.

This driver is using the serial port interface, based on the commands in the [`API documentation`](https://br.omega.com/omegaFiles/software/PX409-USBH_r.html). This driver is developed by the [ConCat lab at TU Berlin](https://tu.berlin/en/concat).

## Installation
Install the package using `pip`, e.g. `pip install tomato-omega`.

## Supported functions

### Capabilities
- `measure_pressure` which measures the temperature on a given serial port (`address`)

### Attributes
- `pressure` which is the current pressure, `pint.Quantity(float, unit)`

### Constants
- `serial` which is the serial number (`str`) of the device,
- `gauge` which is a `bool` indicating whether gauge (`True`) or absolute (`False`) pressure is reported

## Contributors

- Peter Kraus
