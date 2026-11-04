# Third-party dependencies

Original project code uses MIT (root LICENSE). Third-party code retains its own attribution.

Digilent rgb2dvi sources and TMDS definitions are a snapshot of the existing locally used Vivado library, stored in board/vendor/digilent_rgb2dvi.zip with the upstream MIT notice (Copyright 2017 Digilent). Upstream: https://github.com/Digilent/vivado-library and https://raw.githubusercontent.com/Digilent/vivado-library/master/License.txt . Snapshot identity is recorded in file_manifest.json. A source commit was not recorded by the original import, so no commit hash is invented.

PYNQ-Z2 board definitions are the locally used TUL board files, archived separately with original XML metadata. Their original license/provenance must still be confirmed before final public redistribution. This is an open release item, not covered by the project's MIT license.

AMD Vivado/Vitis and PYNQ system images are external dependencies and are not redistributed. PhysioNet source databases and this team's personal ECG recordings are not included. Model weights/configuration are included for inference; dataset access and training snapshot limitations are documented in model/README.md.

Vendor archives preserve upstream internal filename case to avoid breaking IP XML. Repository-owned paths use lowercase ASCII, except README.md and LICENSE, matching the guide's conventional examples.
