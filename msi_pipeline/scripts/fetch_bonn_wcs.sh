#!/usr/bin/env bash
set -euo pipefail

# Fetch Bonn DEM/DSM (and optional nDOM) from NRW WCS.
# Usage:
#   scripts/fetch_bonn_wcs.sh <minx> <miny> <maxx> <maxy>
# Coordinates must be in EPSG:25832 (meters).

if [ "$#" -ne 4 ]; then
  echo "Usage: $0 <minx> <miny> <maxx> <maxy>   (EPSG:25832)"
  exit 1
fi

for cmd in gdal_translate gdalwarp; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing required command: $cmd"
    exit 1
  fi
done

MINX="$1"
MINY="$2"
MAXX="$3"
MAXY="$4"

RAW_DIR="Data/Bonn/raw"
mkdir -p "$RAW_DIR"

# WCS endpoints (NRW)
WCS_DGM="https://www.wcs.nrw.de/geobasis/wcs_nw_dgm"
WCS_DOM="https://www.wcs.nrw.de/geobasis/wcs_nw_dom"
WCS_NDOM="https://www.wcs.nrw.de/geobasis/wcs_nw_ndom"

# Coverage IDs used by NRW services.
COV_DGM="nw_dgm"
COV_DOM="nw_dom"
COV_NDOM="nw_ndom"

echo "Fetching DGM (DEM) ..."
gdal_translate \
  "WCS:${WCS_DGM}?SERVICE=WCS&VERSION=2.0.1&COVERAGEID=${COV_DGM}" \
  "${RAW_DIR}/DEM_bonn_raw.tif" \
  -projwin "$MINX" "$MAXY" "$MAXX" "$MINY" \
  -projwin_srs EPSG:25832

echo "Fetching DOM (DSM) ..."
gdal_translate \
  "WCS:${WCS_DOM}?SERVICE=WCS&VERSION=2.0.1&COVERAGEID=${COV_DOM}" \
  "${RAW_DIR}/DSM_bonn_raw.tif" \
  -projwin "$MINX" "$MAXY" "$MAXX" "$MINY" \
  -projwin_srs EPSG:25832

echo "Trying nDOM (optional canopy/object height) ..."
set +e
gdal_translate \
  "WCS:${WCS_NDOM}?SERVICE=WCS&VERSION=2.0.1&COVERAGEID=${COV_NDOM}" \
  "${RAW_DIR}/nDOM_bonn_raw.tif" \
  -projwin "$MINX" "$MAXY" "$MAXX" "$MINY" \
  -projwin_srs EPSG:25832
NDOM_STATUS=$?
set -e

if [ "$NDOM_STATUS" -ne 0 ]; then
  echo "nDOM request failed. Continuing without nDOM."
  rm -f "${RAW_DIR}/nDOM_bonn_raw.tif"
fi

echo "Raw downloads complete in ${RAW_DIR}"
