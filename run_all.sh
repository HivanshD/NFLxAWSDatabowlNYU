#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 src/build_routes.py
python3 src/chip_extract.py
python3 src/chip_analysis.py
python3 src/chip_figures.py
python3 src/chip_play_field.py
python3 src/chip_route_trees.py
