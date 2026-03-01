#!/usr/bin/env python3
"""
Build a simple UMEP land-cover raster for Bonn.
Classes:
1 Paved, 2 Buildings, 5 Grass, 7 Water (optional mask)

Notes:
- We intentionally avoid classes 3/4 (tree classes) because SOLWEIG expects
  ground cover beneath canopy and will reject raw tree classes in many cases.
- Trees from CDSM are mapped to class 5 (grass/vegetated ground) by default.
"""

from pathlib import Path
import argparse
import numpy as np
from osgeo import gdal


def read_arr(path: Path):
    ds = gdal.Open(str(path))
    if ds is None:
        raise FileNotFoundError(path)
    arr = ds.ReadAsArray().astype(float)
    nd = ds.GetRasterBand(1).GetNoDataValue()
    return ds, arr, nd


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--dem', default='Data/Bonn/processed/DEM_bonn.tif')
    p.add_argument('--dsm', default='Data/Bonn/processed/DSM_bonn.tif')
    p.add_argument('--cdsm', default='Data/Bonn/processed/CDSM_bonn.tif')
    p.add_argument('--water-mask', default='', help='Optional raster mask (water=1) aligned to DEM grid')
    p.add_argument('--building-height-threshold', type=float, default=2.0)
    p.add_argument('--tree-height-threshold', type=float, default=1.5)
    p.add_argument('--out', default='Data/Bonn/processed/landcover_bonn.tif')
    args = p.parse_args()

    dem_ds, dem, nd_dem = read_arr(Path(args.dem))
    _, dsm, nd_dsm = read_arr(Path(args.dsm))
    _, cdsm, nd_cdsm = read_arr(Path(args.cdsm))

    if dem.shape != dsm.shape or dem.shape != cdsm.shape:
        raise ValueError('DEM/DSM/CDSM shapes do not match')

    nodata = -9999
    invalid = np.zeros(dem.shape, dtype=bool)
    if nd_dem is not None:
        invalid |= dem == nd_dem
    if nd_dsm is not None:
        invalid |= dsm == nd_dsm
    if nd_cdsm is not None:
        invalid |= cdsm == nd_cdsm

    h = dsm - dem

    # Default class = paved
    lc = np.full(dem.shape, 1, dtype=np.int16)

    # Buildings
    buildings = h >= args.building_height_threshold
    lc[buildings] = 2

    # Vegetated ground inferred from canopy model (not building)
    vegetation = (cdsm >= args.tree_height_threshold) & (~buildings)
    lc[vegetation] = 5

    # Optional water mask
    if args.water_mask:
        wds, wmask, w_nd = read_arr(Path(args.water_mask))
        if wmask.shape != lc.shape:
            raise ValueError('water mask shape mismatch')
        water = wmask >= 1
        if w_nd is not None:
            water &= wmask != w_nd
        lc[water] = 7
        wds = None

    lc[invalid] = nodata

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    drv = gdal.GetDriverByName('GTiff')
    ods = drv.Create(str(out), dem_ds.RasterXSize, dem_ds.RasterYSize, 1, gdal.GDT_Int16)
    ods.SetGeoTransform(dem_ds.GetGeoTransform())
    ods.SetProjection(dem_ds.GetProjection())
    band = ods.GetRasterBand(1)
    band.WriteArray(lc)
    band.SetNoDataValue(nodata)
    band.FlushCache()
    ods = None
    dem_ds = None

    uniq, cnt = np.unique(lc[lc != nodata], return_counts=True)
    print('Wrote', out)
    print('Class distribution:')
    for u, c in zip(uniq.tolist(), cnt.tolist()):
        print(f'  class {u}: {c}')


if __name__ == '__main__':
    main()
