A Home Assistant Integration with Extron Crosspoint.

Specifically to integrate with an ethernet enabled switcher.

More detail to be added


example configuration.yaml

extron_crosspoint:
  host: 10.0.1.200 # or your local hostname, e.g. extron.local
  port: 23
  inputs:
    1: "NES"
    2: "SNES"
    3: "N64"
    4: "Mega Drive"
    5: "PlayStation 2"
    6: "PC / VGA"
  outputs:
    1: "BVM-D24E1WE Component"
    2: "BBVM-D24E1WE/PVM-20L4 RGB"
