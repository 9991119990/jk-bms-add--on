# JK BMS Home Assistant Add-on

Home Assistant add-on for reading a Jikong/JK BMS over a Jikong RS485 adapter and publishing values to MQTT with Home Assistant discovery.

Tested hardware:

- BMS: `JK_B2A24S15P`
- BMS app setting: `UART1 Protocol No. = JK BMS RS485 Modbus V1.0`
- USB-RS485 adapter: `1a86:55d3 USB Single Serial`
- Serial: `115200`, address `0`

Wiring from Jikong RS485 adapter output to USB-RS485 adapter:

- yellow -> `A`
- white -> `B`
- black -> `GND`

## Installation

In Home Assistant, add this repository to the add-on store:

```text
https://github.com/9991119990/jk-bms-add--on
```

Install add-on `JK BMS RS485 MQTT`, set the serial port and MQTT credentials, then start it.

Recommended serial port path:

```text
/dev/serial/by-id/usb-1a86_USB_Single_Serial_5A9A000831-if00
```

The add-on publishes MQTT discovery config and state under `jk_bms/*`.
