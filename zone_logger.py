import asyncio
import time
import logging
import argparse
import csv
from datetime import datetime
from bleak import BleakClient, BleakScanner

# --- UPDATED UUIDS ---
IFIT_SERVICE_UUID = '00001533-1412-efde-1523-785feabcd123'
IFIT_NOTIFY_CHAR_UUID = '00001535-1412-efde-1523-785feabcd123'
IFIT_COMMAND_CHAR_UUID = '00001534-1412-efde-1523-785feabcd123'

# --- POLAR UUIDS ---
POLAR_HR_UUID = '00002a37-0000-1000-8000-00805f9b34fb'
POLAR_BATT_UUID = '00002a19-0000-1000-8000-00805f9b34fb'
POLAR_HR_SERVICE_UUID = "0000180d-0000-1000-8000-00805f9b34fb"

# --- HEX COMMANDS ---
IFIT_INIT_SEQUENCE = [
    bytes.fromhex("fe022c04"),
    bytes.fromhex("0012020402280428900701cec4b0aaa2a8949696"),
    bytes.fromhex("0112aca8a2bad0dccefe14003a52786486a6fc18"),
    bytes.fromhex("ff08324aa0880200004400000000000000000000")
]

IFIT_POLL_SEQUENCE = [
    bytes.fromhex("fe021403"),
    bytes.fromhex("001202040210041002000a1b9430000040500080"),
    bytes.fromhex("ff02182700000000000000000000000000000000")
]

class IFitDevice:
  def __init__(self, address):
    self.address = address
    self.client = None
    self.speed = 0.0
    self.incline = 0.0
    self.distance = 0.0
    self.connected = False

  async def connect(self):
    logging.info(f"Connecting to iFit at {self.address}...")
    self.client = BleakClient(self.address)
    await self.client.connect()
    self.connected = self.client.is_connected
    logging.info(f"Connected to iFit: {self.connected}")

  async def setup(self):
    if not self.connected:
      return

    # Start Notifications
    await self.client.start_notify(IFIT_NOTIFY_CHAR_UUID, self._notification_handler)

    # Initialization Handshake
    logging.info("Initializing iFit session...")
    for packet in IFIT_INIT_SEQUENCE:
      await self.client.write_gatt_char(IFIT_COMMAND_CHAR_UUID, packet, response=True)

    await asyncio.sleep(2)

  async def update(self):
    if not self.connected:
      return
    try:
      for packet in IFIT_POLL_SEQUENCE:
        await self.client.write_gatt_char(IFIT_COMMAND_CHAR_UUID, packet, response=True)
    except Exception as e:
      logging.error(f"iFit update error: {e}")

  async def close(self):
    if self.client and self.connected:
      try:
        await self.client.stop_notify(IFIT_NOTIFY_CHAR_UUID)
      except Exception:
        pass
      await self.client.disconnect()

  def _notification_handler(self, sender, data: bytearray):
    logging.debug(f'ifit raw data {data.hex()}')
    signature = bytes.fromhex("2e042e02")
    idx = data.find(signature)

    if idx != -1:
      try:
        start = idx + 5
        speed_raw = int.from_bytes(data[start : start + 2], byteorder='little')
        self.speed = speed_raw / 100.0

        incline_raw = int.from_bytes(data[start + 2 : start + 4], byteorder='little')
        self.incline = incline_raw / 100.0

        distance_raw = int.from_bytes(data[start + 6 : start + 8], byteorder='little')
        self.distance = distance_raw / 1000.0
      except (IndexError, ValueError):
        pass

class PolarDevice:
  def __init__(self, address):
    self.address = address
    self.client = None
    self.hr = 0
    self.battery = 0
    self.connected = False
    self._last_battery_read = 0
    self._connection_start = 0

  async def connect(self):
    if not self.address:
      return
    logging.info(f"Connecting to Polar at {self.address}...")
    try:
      self.client = BleakClient(self.address, disconnected_callback=self._on_disconnect, timeout=20.0)
      await self.client.connect()
      await asyncio.sleep(1.0)  # Allow connection to settle
      self.connected = self.client.is_connected
      if self.connected:
        self._connection_start = time.time()
      logging.info(f"Connected to Polar: {self.connected}")
    except Exception as e:
      logging.error(f"Could not connect to Polar: {e}")
      self.connected = False

  def _on_disconnect(self, client):
    logging.warning("Polar disconnected, make sure is PAIRED at OS level!!!")
    self.connected = False

  async def setup(self):
    if not self.connected:
      return

    try:
      await self.client.start_notify(POLAR_HR_UUID, self._hr_handler)
      logging.info("Polar HR notifications started")
    except Exception as e:
      logging.error(f"Polar setup error: {e}")
      self.connected = False

  async def update(self):
    # Ensure internal state matches client state
    if self.client:
      self.connected = self.client.is_connected

    if not self.connected:
      await self.connect()
      if self.connected:
        await self.setup()
      return

    if time.time() - self._last_battery_read > 60:
      try:
        await self._read_battery()
      except Exception as e:
        logging.error(f"Polar keep-alive error: {e}")

  async def _read_battery(self):
    batt = await self.client.read_gatt_char(POLAR_BATT_UUID)
    self.battery = int(batt[0])
    self._last_battery_read = time.time()

  async def close(self):
    if self.client and self.connected:
      try:
        await self.client.stop_notify(POLAR_HR_UUID)
        await self.client.disconnect()
      except Exception:
        pass

  def _hr_handler(self, sender, data: bytearray):
    logging.debug(f'polar raw data {data.hex()}')
    try:
      if not data:
        return
      flags = data[0]
      hr_fmt = flags & 0x01
      hr_val = data[1] if hr_fmt == 0 else int.from_bytes(data[1:3], byteorder='little')
      self.hr = hr_val
    except Exception:
      pass

async def main():
  parser = argparse.ArgumentParser(description="iFit and Polar Bluetooth Monitor - Zone Training")
  parser.add_argument("-d", "--debug", action="store_true", help="Enable debug logging")
  args = parser.parse_args()

  log_level = logging.DEBUG if args.debug else logging.INFO
  logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')
  logging.info("Scanning for devices...")
  ifit, ifit_address = None, None
  polar, polar_address = None, None

  devices = await BleakScanner.discover(return_adv=True)
  for d, adv in devices.values():
    if not ifit_address and IFIT_SERVICE_UUID.lower() in [u.lower() for u in adv.service_uuids]:
      print(f"Found iFit: {d.name} [{d.address}]")
      ifit_address = d.address

    if not polar_address:
      if (POLAR_HR_SERVICE_UUID in [u.lower() for u in adv.service_uuids]) or (d.name and "Polar" in d.name):
        logging.info(f"Found Polar: {d.name} [{d.address}]")
        polar_address = d.address


  if ifit_address:
    ifit = IFitDevice(ifit_address)
    await ifit.connect()
  else:
    logging.warning("iFit device not found. Ensure the treadmill is on.")

  if polar_address:
    polar = PolarDevice(polar_address)
    await polar.connect()
  else:
    logging.warning("Polar device not found. Ensure the HR monitor is on.")

  try:
    if ifit:
      await ifit.setup()
    if polar:
      await polar.setup()
      # Read battery once at the beginning
      await polar.update()
      logging.info(f"Polar Battery: {polar.battery}%")

    await asyncio.sleep(3)

    # CSV Logging Setup
    filename = datetime.now().strftime("%Y%m%d-%H%M") + ".csv"
    logging.info(f"Logging data to {filename}")

    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
      csv_writer = csv.writer(csvfile)
      header = ['timestamp', 'speed_kmh', 'incline_percent', 'distance_km', 'hr_bpm']
      csv_writer.writerow(header)

      logging.info("Starting data poll (Ctrl+C to quit)...")
      while True:
        log_items = []
        if ifit:
          await ifit.update()
          log_items.append(f"Speed: {ifit.speed:.2f} km/h")
          log_items.append(f"Incline: {ifit.incline:.1f}%")
          log_items.append(f"Dist: {ifit.distance:.3f} km")
        if polar:
          await polar.update()
          log_items.append(f"HR: {polar.hr} bpm")
        logging.info(", ".join(log_items))

        # Write to CSV
        csv_writer.writerow([
          datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
          ifit.speed if ifit else None,
          ifit.incline if ifit else None,
          ifit.distance if ifit else None,
          polar.hr if polar else None
        ])

        await asyncio.sleep(1)

  except KeyboardInterrupt:
    logging.info("Stopping...")
  finally:
    if ifit:
      await ifit.close()
    if polar:
      await polar.close()

if __name__ == "__main__":
  asyncio.run(main())
