# Kotilaitteet

A command-line tool to manage home electronic devices – either manually or automatically based on Finnish electricity spot prices.

## Features

- **Auto-discovery** – scan the local WLAN for connected devices (uses `nmap` when available, falls back to the ARP table)
- **Device registry** – add, remove and list devices; state is persisted in `~/.kotilaitteet/devices.json`
- **Manual control** – turn devices on/off or toggle them from the command line
- **Electricity prices** – fetch today's Finnish spot prices from the public [spot-hinta.fi](https://spot-hinta.fi/) API
- **Smart scheduling** – per-device configuration of minimum daily runtime and a price threshold; the tool recommends which hours to activate each device

## Requirements

- Python 3.11+
- `nmap` (optional, for better network scanning)

## Installation

```bash
pip install .
```

This installs the `kotilaitteet` command.

## Quick start

### 1 · Discover devices on your WLAN

```bash
kotilaitteet scan
# or specify the subnet manually:
kotilaitteet scan --network 192.168.1.0/24
```

Example output:

```
Scanning network…

Found 4 device(s):

IP               MAC                HOSTNAME                       Vendor
--------------------------------------------------------------------------------
192.168.1.1      b0:be:76:aa:bb:cc  router.local                   TP-Link
192.168.1.10     50:c7:bf:11:22:33  boiler.local                   TP-Link
192.168.1.20     b8:27:3b:44:55:66  raspberrypi.local              Raspberry Pi
192.168.1.30     00:17:88:77:88:99  hue-bridge.local               Philips Hue
```

### 2 · Register a device

```bash
kotilaitteet add --name "Boiler" --ip 192.168.1.10 --mac 50:c7:bf:11:22:33 --type heater
```

### 3 · Manual control

```bash
kotilaitteet on  --name "Boiler"
kotilaitteet off --mac  50:c7:bf:11:22:33
kotilaitteet toggle --name "Boiler"
```

### 4 · List registered devices

```bash
kotilaitteet list
```

### 5 · View today's electricity prices

```bash
kotilaitteet prices
kotilaitteet prices --cheapest 5   # highlight 5 cheapest hours
```

### 6 · Enable price-based control

```bash
# Run at least 4 hours/day during the cheapest hours,
# and never when the price exceeds 15 c/kWh:
kotilaitteet price-control --enable \
    --name "Boiler" \
    --hours 4 \
    --threshold 15

# Disable later:
kotilaitteet price-control --disable --name "Boiler"
```

### 7 · View the daily schedule

```bash
kotilaitteet schedule

# Apply the recommendation for the current hour:
kotilaitteet schedule --apply
```

Example output:

```
Schedule for 'Boiler' (2024-01-15):

  Hour     State  Price (c/kWh)    Reason
  ----------------------------------------------------------------------
  00:00    ON      2.00             Among 4 cheapest hours (2.00 c/kWh)
  01:00    ON      2.50             Among 4 cheapest hours (2.50 c/kWh)
  02:00    ON      3.00             Among 4 cheapest hours (3.00 c/kWh)
  03:00    ON      3.50             Among 4 cheapest hours (3.50 c/kWh)
  04:00    OFF     4.00             Outside cheapest window (4.00 c/kWh)
  ...
  15:00    OFF    16.00             Price 16.00 c/kWh exceeds threshold 15.00 c/kWh
```

### 8 · Overall status

```bash
kotilaitteet status
```

## All commands

| Command         | Description |
|-----------------|-------------|
| `scan`          | Discover devices on the local network |
| `list`          | List registered devices |
| `status`        | Show device states and current price recommendations |
| `add`           | Register a new device |
| `remove`        | Remove a registered device |
| `on`            | Turn a device on |
| `off`           | Turn a device off |
| `toggle`        | Toggle a device on/off |
| `prices`        | Show today's electricity spot prices |
| `price-control` | Configure price-based automation |
| `schedule`      | Show (and optionally apply) the daily schedule |

Run `kotilaitteet <command> --help` for details on each command.

## Running as a cron job

To apply the price-based schedule automatically every hour:

```cron
0 * * * * /usr/local/bin/kotilaitteet schedule --apply >> /var/log/kotilaitteet.log 2>&1
```

## Development

```bash
pip install -e .
pip install pytest
python -m pytest tests/ -v
```
