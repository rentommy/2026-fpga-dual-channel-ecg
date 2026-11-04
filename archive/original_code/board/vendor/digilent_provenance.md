# Digilent RGB-to-DVI core

Source: https://github.com/Digilent/vivado-library (official Digilent repository).
Retrieved 2026-10-23 from the master-branch ZIP. Archive SHA256:
`2c988887589fad6c5de783aa5b5299985dd788f2488e585cfdb3a0e36c734404`.

Only `ip/rgb2dvi/` and `if/tmds_v1_0/` are used. Vendor HDL headers retain the
full BSD 3-clause license, copyright and disclaimer. The vendor core is unmodified.
The project supplies external pixel/serial clocks and adapts its expected R,B,G
byte order at the application boundary. Original IP version is 1.4.
