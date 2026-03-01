# Bonn Data Collection for UMEP SOLWEIG

This project now uses Bonn-specific inputs instead of the tutorial sample.

## 1) Required inputs (minimum)

- `DEM` (ground elevation raster, meters)
- `DSM` (surface elevation raster, meters)
- `MET` forcing file in UMEP/SOLWEIG format (24 columns; generated later)

## 2) Optional but recommended

- `CDSM` (canopy height raster)
- `Land cover` raster for UMEP classes

## 3) Recommended sources for Bonn (NRW)

- DGM1 (DEM):
  - Download root: `https://www.opengeodata.nrw.de/produkte/geobasis/hm/dgm1_tiff/dgm1_tiff/`
  - WCS endpoint: `https://www.wcs.nrw.de/geobasis/wcs_nw_dgm`
- DOM1 (DSM):
  - WCS endpoint: `https://www.wcs.nrw.de/geobasis/wcs_nw_dom`
- nDOM (optional canopy/object height candidate):
  - WCS endpoint: `https://www.wcs.nrw.de/geobasis/wcs_nw_ndom`

## 4) Target format before running SOLWEIG

All rasters must be:
- same CRS (recommended `EPSG:25832`)
- same pixel size (recommended 1 m for NRW data)
- same extent / alignment
- single-band GeoTIFF
- NoData set consistently

Expected output files from our prep scripts:
- `Data/Bonn/processed/DEM_bonn.tif`
- `Data/Bonn/processed/DSM_bonn.tif`
- `Data/Bonn/processed/CDSM_bonn.tif` (optional)

## 5) Area of interest (AOI)

Create an AOI polygon in:
- `Data/Bonn/aoi/bonn_aoi.geojson`

Use EPSG:25832 if possible.

## 6) Next step

After collecting/normalizing spatial data, we generate or prepare the meteorological forcing file and then run SOLWEIG on Bonn.
