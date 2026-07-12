#!/usr/bin/env python3
import argparse
import glob
import json
import os
import socket
import time

from read_jk_bms import COMMANDS, configure_port, decode, read_payload


SENSORS = [
    ("voltage_v", "Voltage", "V", "voltage"),
    ("current_a", "Current", "A", "current"),
    ("power_w", "Power", "W", "power"),
    ("soc_percent", "SOC", "%", "battery"),
    ("soh_percent", "SOH", "%", None),
    ("remaining_capacity_ah", "Remaining capacity", "Ah", None),
    ("nominal_capacity_ah", "Nominal capacity", "Ah", None),
    ("cycles", "Cycles", None, None),
    ("delta_cell_mv", "Cell delta", "mV", "voltage"),
    ("mos_temp_c", "MOS temperature", "°C", "temperature"),
    ("temp1_c", "Temperature 1", "°C", "temperature"),
    ("temp2_c", "Temperature 2", "°C", "temperature"),
    ("max_charge_current_a", "Max charge current", "A", "current"),
    ("max_discharge_current_a", "Max discharge current", "A", "current"),
]

BINARY_SENSORS = [
    ("balancing", "Balancing"),
    ("charge_fet", "Charge FET"),
    ("discharge_fet", "Discharge FET"),
    ("heating", "Heating"),
]


def enc_str(value: str) -> bytes:
    data = value.encode()
    return len(data).to_bytes(2, "big") + data


def enc_len(length: int) -> bytes:
    out = bytearray()
    while True:
        digit = length % 128
        length //= 128
        if length:
            digit |= 0x80
        out.append(digit)
        if not length:
            return bytes(out)


class MqttClient:
    def __init__(self, host, port, username=None, password=None, client_id="jk-bms-rs485"):
        self.sock = socket.create_connection((host, port), timeout=10)
        self.username = username
        self.password = password
        self.client_id = client_id
        self._connect()

    def _send(self, packet_type: int, flags: int, payload: bytes) -> None:
        self.sock.sendall(bytes([(packet_type << 4) | flags]) + enc_len(len(payload)) + payload)

    def _connect(self) -> None:
        flags = 0x02
        payload = enc_str(self.client_id)
        if self.username is not None:
            flags |= 0x80
            payload += enc_str(self.username)
        if self.password is not None:
            flags |= 0x40
            payload += enc_str(self.password)
        variable = enc_str("MQTT") + bytes([4, flags, 0, 60])
        self._send(1, 0, variable + payload)
        response = self.sock.recv(4)
        if len(response) < 4 or response[0] != 0x20 or response[3] != 0:
            raise RuntimeError(f"MQTT connect failed: {response.hex(' ')}")

    def publish(self, topic: str, payload, retain=False) -> None:
        if not isinstance(payload, str):
            payload = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        flags = 0x01 if retain else 0x00
        self._send(3, flags, enc_str(topic) + payload.encode())

    def close(self) -> None:
        try:
            self._send(14, 0, b"")
        finally:
            self.sock.close()


def read_bms(port: str, baud: int, address: int) -> dict:
    with open(port, "rb+", buffering=0) as serial_port:
        fd = serial_port.fileno()
        configure_port(fd, baud)
        settings = read_payload(fd, address, COMMANDS["settings"])
        status = read_payload(fd, address, COMMANDS["status"])
        about = read_payload(fd, address, COMMANDS["about"])
    return decode(status, settings, about)


def resolve_port(configured_port: str) -> str:
    candidates = [configured_port, "/dev/ttyACM0"]
    candidates.extend(sorted(glob.glob("/dev/serial/by-id/*")))
    candidates.extend(sorted(glob.glob("/dev/ttyACM*")))
    candidates.extend(sorted(glob.glob("/dev/ttyUSB*")))

    seen = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if os.path.exists(candidate):
            if candidate != configured_port:
                print(f"Configured serial port {configured_port} is not available, using {candidate}", flush=True)
            return candidate
    return configured_port


def discovery_config(
    name,
    key,
    state_topic,
    device,
    unit=None,
    device_class=None,
    binary=False,
    suggested_display_precision=None,
):
    cfg = {
        "name": name,
        "unique_id": f"jk_bms_{key}",
        "state_topic": state_topic,
        "availability_topic": "jk_bms/availability",
        "device": device,
    }
    if binary:
        cfg["payload_on"] = "true"
        cfg["payload_off"] = "false"
        cfg["value_template"] = "{{ value_json." + key + " | lower }}"
    else:
        cfg["value_template"] = "{{ value_json." + key + " }}"
        if unit:
            cfg["unit_of_measurement"] = unit
        if device_class:
            cfg["device_class"] = device_class
        if suggested_display_precision is not None:
            cfg["suggested_display_precision"] = suggested_display_precision
        if key.endswith("_v") or key.endswith("_a") or key.endswith("_w") or key.endswith("_c"):
            cfg["state_class"] = "measurement"
    return cfg


def publish_discovery(client: MqttClient, state_topic: str, sample: dict) -> None:
    device = {
        "identifiers": ["jk_bms_rs485"],
        "name": "JK BMS RS485",
        "manufacturer": "Jikong",
        "model": sample.get("model"),
        "sw_version": sample.get("software_version"),
    }
    for key, name, unit, device_class in SENSORS:
        topic = f"homeassistant/sensor/jk_bms/{key}/config"
        precision = 3 if key.endswith("_v") else None
        client.publish(
            topic,
            discovery_config(name, key, state_topic, device, unit, device_class, suggested_display_precision=precision),
            retain=True,
        )
    for key, name in BINARY_SENSORS:
        topic = f"homeassistant/binary_sensor/jk_bms/{key}/config"
        client.publish(topic, discovery_config(name, key, state_topic, device, binary=True), retain=True)
    for idx in range(1, int(sample.get("cell_count", 0)) + 1):
        key = f"cell_{idx:02d}_v"
        topic = f"homeassistant/sensor/jk_bms/{key}/config"
        cfg = discovery_config(
            f"Cell {idx:02d}",
            key,
            state_topic,
            device,
            "V",
            "voltage",
            suggested_display_precision=3,
        )
        client.publish(topic, cfg, retain=True)


def flatten_cells(data: dict) -> dict:
    out = dict(data)
    for idx, voltage in enumerate(data.get("cell_voltages_v", []), 1):
        out[f"cell_{idx:02d}_v"] = voltage
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="/dev/ttyACM0")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--address", type=lambda value: int(value, 0), default=0)
    parser.add_argument("--mqtt-host", required=True)
    parser.add_argument("--mqtt-port", type=int, default=1883)
    parser.add_argument("--mqtt-user")
    parser.add_argument("--mqtt-password")
    parser.add_argument("--interval", type=float, default=10)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    state_topic = "jk_bms/state"
    while True:
        client = None
        try:
            port = resolve_port(args.port)
            data = flatten_cells(read_bms(port, args.baud, args.address))
            client = MqttClient(args.mqtt_host, args.mqtt_port, args.mqtt_user, args.mqtt_password)
            publish_discovery(client, state_topic, data)
            client.publish("jk_bms/availability", "online", retain=True)
            client.publish(state_topic, data, retain=False)
            print(
                f"Published JK BMS data: {data.get('voltage_v')}V "
                f"{data.get('current_a')}A SOC={data.get('soc_percent')}%",
                flush=True,
            )
        except Exception as exc:
            print(f"Read/publish failed: {exc}", flush=True)
        finally:
            if client is not None:
                client.close()
        if args.once:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
