A Home Assistant Integration with Extron Crosspoint.

Specifically to integrate with an ethernet enabled switcher.

More detail to be added


example configuration.yaml

```
extron_crosspoint:
  host: 10.0.1.200 # or your local hostname
  port: 23
  # Output 1: Component
  # Output 2 RGB
  
  sources:
  
    chromecast:
      name: "Chromecast"
      input: 1 # Input 1 on matrix
      video_out: 1 # Output 1 (BVM/PVM RGB)
      audio_out: 1 # Output 1 (Amp)
      
    xbox:
      name: "Xbox"
      input: 2
      video_out: 1 # Component
      audio_out: 1 # Amp

    saturn:
      name: "Saturn"
      input: 3
      video_out: 2 # RGB
      audio_out: 1 # Amp
```
