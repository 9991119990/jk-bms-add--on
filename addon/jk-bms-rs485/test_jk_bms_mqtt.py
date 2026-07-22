#!/usr/bin/env python3
import importlib.util
import pathlib
import sys
import unittest
from types import SimpleNamespace


MODULE_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(MODULE_DIR))
spec = importlib.util.spec_from_file_location("jk_bms_mqtt", MODULE_DIR / "jk_bms_mqtt.py")
jk_bms_mqtt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(jk_bms_mqtt)


class FakeMqttClient:
    instances = []

    def __init__(self, *args, **kwargs):
        self.published = []
        self.closed = False
        FakeMqttClient.instances.append(self)

    def publish(self, topic, payload, retain=False):
        self.published.append((topic, payload, retain))

    def close(self):
        self.closed = True


class JkBmsMqttTests(unittest.TestCase):
    def setUp(self):
        FakeMqttClient.instances = []

    def test_run_iteration_publishes_offline_when_bms_read_fails(self):
        args = SimpleNamespace(
            port="/dev/ttyACM0",
            baud=115200,
            address=0,
            mqtt_host="core-mosquitto",
            mqtt_port=1883,
            mqtt_user="",
            mqtt_password="",
        )

        def failing_read_bms(port, baud, address):
            raise RuntimeError("No JK payload received")

        ok = jk_bms_mqtt.run_iteration(
            args,
            mqtt_client_cls=FakeMqttClient,
            read_bms_fn=failing_read_bms,
        )

        self.assertFalse(ok)
        self.assertEqual(len(FakeMqttClient.instances), 1)
        self.assertIn(("jk_bms/availability", "offline", True), FakeMqttClient.instances[0].published)
        self.assertTrue(FakeMqttClient.instances[0].closed)

    def test_run_iteration_publishes_state_and_online_when_bms_read_succeeds(self):
        args = SimpleNamespace(
            port="/dev/ttyACM0",
            baud=115200,
            address=0,
            mqtt_host="core-mosquitto",
            mqtt_port=1883,
            mqtt_user="",
            mqtt_password="",
        )

        def successful_read_bms(port, baud, address):
            return {
                "model": "JK",
                "software_version": "1.0",
                "cell_count": 1,
                "cell_voltages_v": [3.31],
                "voltage_v": 53.0,
                "current_a": 1.5,
                "power_w": 79.5,
            }

        ok = jk_bms_mqtt.run_iteration(
            args,
            mqtt_client_cls=FakeMqttClient,
            read_bms_fn=successful_read_bms,
        )

        self.assertTrue(ok)
        published = FakeMqttClient.instances[0].published
        self.assertIn(("jk_bms/availability", "online", True), published)
        self.assertTrue(any(topic == "jk_bms/state" and payload["cell_01_v"] == 3.31 for topic, payload, _ in published))


if __name__ == "__main__":
    unittest.main()
