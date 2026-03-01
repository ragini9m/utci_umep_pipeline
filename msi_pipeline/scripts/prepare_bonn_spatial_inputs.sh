#!/usr/bin/env bash
set -euo pipefail

# Normalize raw Bonn rasters to UMEP-ready aligned GeoTIFFs.
# Inputs expected in Data/Bonn/raw:
#   DEM_bonn_raw.tif
#   DSM_bonn_raw.tif
#   (optional) nDOM_bonn_raw.tif

for cmd in gdalwarp gdalinfo gdal_calc.py; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing required command: $cmd"
    exit 1
  fi
done

RAW_DIR="Data/Bonn/raw"
OUT_DIR="Data/Bonn/processed"
mkdir -p "$OUT_DIR"

DEM_RAW="${RAW_DIR}/DEM_bonn_raw.tif"
DSM_RAW="${RAW_DIR}/DSM_bonn_raw.tif"
NDOM_RAW="${RAW_DIR}/nDOM_bonn_raw.tif"

if [ ! -f "$DEM_RAW" ] || [ ! -f "$DSM_RAW" ]; then
  echo "Missing ${DEM_RAW} or ${DSM_RAW}."
  echo "Run scripts/fetch_bonn_wcs.sh first or place files manually."
  exit 1
fi

DEM_OUT="${OUT_DIR}/DEM_bonn.tif"
DSM_OUT="${OUT_DIR}/DSM_bonn.tif"
CDSM_OUT="${OUT_DIR}/CDSM_bonn.tif"

# Use DEM as reference grid for alignment.
echo "Preparing DEM ..."
gdalwarp -overwrite \
  -t_srs EPSG:25832 \
  -r bilinear \
  -tr 1 1 \
  -dstnodata -9999 \
  "$DEM_RAW" "$DEM_OUT"

echo "Preparing DSM aligned to DEM ..."
gdalwarp -overwrite \
  -t_srs EPSG:25832 \
  -r bilinear \
  -tr 1 1 \
  -te $(gdalinfo "$DEM_OUT" | awk '/Upper Left/{gsub(/[(),]/,""); ulx=$3; uly=$4} /Lower Right/{gsub(/[(),]/,""); lrx=$3; lry=$4} END{print ulx, lry, lrx, uly}') \
  -tap \
  -dstnodata -9999 \
  "$DSM_RAW" "$DSM_OUT"

if [ -f "$NDOM_RAW" ]; then
  echo "Preparing CDSM from nDOM (negative values clamped to 0) ..."
  TMP_NDOM="${OUT_DIR}/_nDOM_aligned_tmp.tif"
  gdalwarp -overwrite \
    -t_srs EPSG:25832 \
    -r bilinear \
    -tr 1 1 \
    -te $(gdalinfo "$DEM_OUT" | awk '/Upper Left/{gsub(/[(),]/,""); ulx=$3; uly=$4} /Lower Right/{gsub(/[(),]/,""); lrx=$3; lry=$4} END{print ulx, lry, lrx, uly}') \
    -tap \
    -dstnodata -9999 \
    "$NDOM_RAW" "$TMP_NDOM"

  gdal_calc.py -A "$TMP_NDOM" --outfile="$CDSM_OUT" --calc="maximum(A,0)" --NoDataValue=-9999 --quiet
  rm -f "$TMP_NDOM"
else
  echo "No nDOM found. Creating zero CDSM (no vegetation for first run)."
  gdal_calc.py -A "$DEM_OUT" --outfile="$CDSM_OUT" --calc="A*0" --NoDataValue=-9999 --quiet
fi

echo "Validation summary:"
for f in "$DEM_OUT" "$DSM_OUT" "$CDSM_OUT"; do
  echo "--- $f"
  gdalinfo "$f" | awk '/Size is|Pixel Size|Coordinate System is|NoData Value/'
done

echo "Done. UMEP-ready spatial inputs are in ${OUT_DIR}"
