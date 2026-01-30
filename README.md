# iFit & Polar Training Zone Monitor

This project enables real-time monitoring and data logging for iFit-enabled treadmills and Polar Heart Rate monitors using Bluetooth Low Energy (BLE).

The primary goal is health monitoring and training evaluation, specifically focusing on the ability to maintain the user at the top of **Zone 2** while maximizing training conditions.

References:

- [Reversing Treadmill Bluetooth - Analyzing Reads](https://taylorbowland.com/posts/treadmill-analyzing-reads/)

## Features

- **Auto-Discovery**: Automatically scans and connects to available iFit treadmills and Polar HR sensors.
- **Real-time Metrics**: Reads speed, incline, and distance from iFit devices.
- **Heart Rate Monitoring**: Reads BPM and battery level from Polar devices.
- **Data Logging**: Saves workout data to timestamped CSV files (e.g., `20260130-1200.csv`) for evaluating Zone 2 adherence.
- **Robust Connection**: Includes reconnection logic for heart rate monitors.

## Prerequisites

- Python 3.8 or higher
- Bluetooth adapter (supported by Bleak)

## Installation

1. Install the required Python dependencies:

```bash
pip install bleak
```

## Usage

### Main Monitor

First pair the Polar device, then run the main script to start scanning and logging to a csv file:

```bash
python zone_logger.py
```

To enable verbose debug logging:

```bash
python zone_logger.py --debug
```

The script will:
1. Scan for compatible devices.
2. Connect to the found iFit and Polar devices.
3. Display metrics in the console.
4. Log data to a CSV file in the current directory.
