#!/usr/bin/with-contenv sh
set -eu

CONFIG=/data/options.json

serial_port=$(python3 -c 'import json; print(json.load(open("/data/options.json"))["serial_port"])')
baud=$(python3 -c 'import json; print(json.load(open("/data/options.json"))["baud"])')
address=$(python3 -c 'import json; print(json.load(open("/data/options.json"))["address"])')
mqtt_host=$(python3 -c 'import json; print(json.load(open("/data/options.json"))["mqtt_host"])')
mqtt_port=$(python3 -c 'import json; print(json.load(open("/data/options.json"))["mqtt_port"])')
mqtt_user=$(python3 -c 'import json; print(json.load(open("/data/options.json"))["mqtt_user"])')
mqtt_password=$(python3 -c 'import json; print(json.load(open("/data/options.json"))["mqtt_password"])')
interval=$(python3 -c 'import json; print(json.load(open("/data/options.json"))["interval"])')

echo "Starting JK BMS RS485 MQTT bridge"
echo "Serial port: ${serial_port}"
echo "MQTT broker: ${mqtt_host}:${mqtt_port}"
echo "Interval: ${interval}s"
echo "Visible serial devices:"
ls -l /dev/ttyACM* /dev/ttyUSB* /dev/serial/by-id/* 2>/dev/null || true

exec python3 /app/jk_bms_mqtt.py \
  --port "${serial_port}" \
  --baud "${baud}" \
  --address "${address}" \
  --mqtt-host "${mqtt_host}" \
  --mqtt-port "${mqtt_port}" \
  --mqtt-user "${mqtt_user}" \
  --mqtt-password "${mqtt_password}" \
  --interval "${interval}"
