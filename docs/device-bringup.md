# Device Bring-Up Checklist

Use this when the ESP32 device is back on the same network as `AnomalyGuard`.

## 1. Backend preflight

- Confirm `AnomalyGuard` backend is running on a reachable host and port.
- Confirm `DEVICE_API_KEY` is set in `backend/.env`.
- Confirm the backend host IP is reachable from the ESP32 Wi-Fi network.
- Confirm these endpoints respond:
  - `POST /api/device/telemetry`
  - `GET /api/device/control/{station_id}`
  - `PUT /api/device/control/{station_id}`

## 2. Laptop-only smoke test first

Before touching the device, simulate it from your laptop:

```powershell
.\scripts\device-smoke-test.ps1 -BaseUrl http://localhost:8000
```

Expected result:

- a device station appears in `/api/stations`
- `GET /api/device/status` shows the station
- a reading is inserted into the anomaly pipeline
- `PUT /api/device/control/{station_id}` updates control state
- `GET /api/device/control/{station_id}` returns the latest control payload

## 3. Firmware configuration

Update these constants in `wastewatermonitor_device/hardware/src/main.cpp`:

- `ANOMALYGUARD_BASE_URL`
- `DEVICE_API_KEY`
- `DEVICE_STATION_ID`
- `DEVICE_STATION_NAME`
- `DEVICE_REGION`

Use the same `DEVICE_API_KEY` value as the backend.

## 4. Device network bring-up

- Power the ESP32 and open the Wi-Fi provisioning portal from `WiFiManager`.
- Join the device to the same network as the backend.
- Open serial monitor at `115200`.
- Confirm serial logs show:
  - Wi-Fi connected
  - time synchronized
  - control poll success or telemetry success

## 5. Dashboard checks

In the `AnomalyGuard` frontend:

- confirm the device station appears in the station selector
- confirm `Device Station` panel shows `Last Seen`
- confirm water temp, humidity, and load-cell values update
- confirm readings show up in the main water-signal chart
- confirm alerts appear if values are outside expected range

## 6. Control loop checks

From the dashboard:

- toggle `Pump`
- toggle `Feeding`
- set feed time and feed weight
- change direction and push control

On the device:

- relay state changes
- servo feeding state changes
- movement pins change with direction

## 7. Useful failure checks

If the device does not appear:

- verify backend IP is correct in firmware
- verify `DEVICE_API_KEY` matches
- verify the device and backend are on the same network
- verify backend port `8000` is not blocked by firewall

If telemetry appears but control does not:

- call `GET /api/device/control/{station_id}` from laptop first
- verify the device station id matches exactly
- verify admin control updates are actually being pushed

If anomaly output looks odd:

- remember the current firmware does not send true `turbidity`, `do_mg_l`, or `flow_l_min`
- the backend currently infers these fields until real sensors are added
