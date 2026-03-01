#!/usr/bin/env python3
import os
import sys
import shutil
import tempfile
import zipfile
from pathlib import Path

import numpy as np
from osgeo import gdal

# Workspace-local runtime dirs
workspace = Path(__file__).resolve().parent
os.environ['XDG_DATA_HOME'] = str(workspace / '.xdg_data')
os.environ['XDG_CONFIG_HOME'] = str(workspace / '.xdg_config')
os.environ['NUMBA_CACHE_DIR'] = str(workspace / '.numba_cache')
(workspace / '.xdg_data').mkdir(parents=True, exist_ok=True)
(workspace / '.xdg_config').mkdir(parents=True, exist_ok=True)
(workspace / '.numba_cache').mkdir(parents=True, exist_ok=True)

# Writable local UMEP plugin copy
source_umep = Path('/home/ginira/.local/share/QGIS/QGIS3/profiles/default/python/plugins/processing_umep')
local_plugins = workspace / '.qgis_plugins'
local_umep = local_plugins / 'processing_umep'
local_plugins.mkdir(parents=True, exist_ok=True)
if not local_umep.exists():
    shutil.copytree(source_umep, local_umep)

# QGIS + plugins imports
sys.path.append('/usr/share/qgis/python')
sys.path.append('/usr/share/qgis/python/plugins')
sys.path.insert(0, str(local_plugins))
sys.path.append('/home/ginira/.local/share/QGIS/QGIS3/profiles/default/python/plugins')

from qgis.core import QgsApplication, QgsPointXY

QgsApplication.setPrefixPath('/usr', True)
qgs = QgsApplication([], False)
qgs.initQgis()

import processing
from processing.core.Processing import Processing
Processing.initialize()

from processing_umep.processing_umep_provider import ProcessingUMEPProvider
umep_provider = ProcessingUMEPProvider()
QgsApplication.processingRegistry().addProvider(umep_provider)

# Patch SuPy ERA5 download behavior for new CDS responses:
# CDS can return ZIP payloads even when "format=netcdf". SuPy expects a plain
# NetCDF file and crashes when xarray opens the zipped file with .nc suffix.
try:
    import pandas as pd
    import supy.util._era5 as _era5

    _orig_download_cds = _era5.download_cds
    _orig_format_df_forcing = _era5.format_df_forcing

    def _download_cds_unzip_aware(fn, dict_req):
        _orig_download_cds(fn, dict_req)
        path_fn = Path(fn)
        if not path_fn.exists():
            return

        # If payload is zip, extract and merge all .nc members (CDS can split
        # variables by stepType, e.g. instant vs accum).
        if zipfile.is_zipfile(path_fn):
            import xarray as xr
            with tempfile.TemporaryDirectory() as td:
                with zipfile.ZipFile(path_fn, "r") as zf:
                    nc_members = [n for n in zf.namelist() if n.lower().endswith(".nc")]
                    members = nc_members if nc_members else zf.namelist()
                    if not members:
                        raise RuntimeError(f"ZIP payload has no members: {path_fn}")

                    extracted_files = []
                    for member in members:
                        zf.extract(member, td)
                        extracted_files.append(Path(td) / member)

                    path_fn.unlink(missing_ok=True)
                    if len(extracted_files) == 1:
                        # Use copy for cross-filesystem compatibility (/tmp -> workspace).
                        shutil.copy2(extracted_files[0], path_fn)
                    else:
                        dsets = [xr.open_dataset(p) for p in extracted_files]
                        try:
                            merged = xr.merge(dsets, compat='override', join='outer')
                            merged.to_netcdf(path_fn)
                        finally:
                            for ds in dsets:
                                ds.close()

    _era5.download_cds = _download_cds_unzip_aware

    # Patch SuPy formatter for pandas/xarray versions returning MultiIndex
    # (e.g. levels like number/expver/time). SuPy expects a DatetimeIndex.
    def _format_df_forcing_index_aware(df_forcing_raw):
        df = df_forcing_raw.copy()
        idx = df.index
        if not hasattr(idx, "year"):
            dt = None
            if isinstance(idx, pd.MultiIndex):
                for i in range(idx.nlevels):
                    vals = idx.get_level_values(i)
                    if isinstance(vals, pd.DatetimeIndex):
                        dt = vals
                        break
                    try:
                        if np.issubdtype(vals.dtype, np.datetime64):
                            dt = pd.DatetimeIndex(vals)
                            break
                    except Exception:
                        pass
            else:
                try:
                    dt = pd.DatetimeIndex(pd.to_datetime(idx))
                except Exception:
                    dt = None

            if dt is not None:
                df.index = dt

        return _orig_format_df_forcing(df)

    _era5.format_df_forcing = _format_df_forcing_index_aware
except Exception as _patch_err:
    print(f"WARNING: Could not patch SuPy ERA5 download handler: {_patch_err}")

base = Path(os.environ.get('BONN_INPUT_DIR', 'Data/Bonn/processed'))
output = Path(os.environ.get('BONN_OUTPUT_DIR', 'bonn_output_final'))
met_dir = Path(os.environ.get('BONN_MET_DIR', 'Data/Bonn/met'))
start_date = os.environ.get('BONN_MET_START', '2024-06-01')
end_date = os.environ.get('BONN_MET_END', '2024-06-03')
fetch_met = os.environ.get('BONN_FETCH_MET', '1') == '1'
all_outputs = os.environ.get('BONN_ALL_OUTPUTS', '0') == '1'
use_lc = os.environ.get('BONN_USE_LC', '1') == '1'
require_lc = os.environ.get('BONN_REQUIRE_LC', '0') == '1'
lc_path = Path(os.environ.get('BONN_LC_PATH', str(base / 'landcover_bonn.tif')))

output.mkdir(exist_ok=True)
met_dir.mkdir(parents=True, exist_ok=True)
svf_dir = output / 'svf'
svf_dir.mkdir(exist_ok=True)
solweig_dir = output / 'solweig'
solweig_dir.mkdir(exist_ok=True)

required = [base / 'DSM_bonn.tif', base / 'DEM_bonn.tif', base / 'CDSM_bonn.tif']
missing = [str(p) for p in required if not p.exists()]
if missing:
    raise FileNotFoundError('Missing required files:\n' + '\n'.join(missing))

if use_lc and not lc_path.exists():
    msg = f'Land cover requested but not found: {lc_path}'
    if require_lc:
        raise FileNotFoundError(msg)
    print(f'WARNING: {msg}. Continuing without land cover.')
    use_lc = False

# AOI center from DEM in EPSG:25832
_d = gdal.Open(str(base / 'DEM_bonn.tif'))
gt = _d.GetGeoTransform()
cols = _d.RasterXSize
rows = _d.RasterYSize
center_x = gt[0] + cols * gt[1] / 2.0
center_y = gt[3] + rows * gt[5] / 2.0
_d = None


def is_valid_solweig_met(path: Path) -> bool:
    try:
        data = np.loadtxt(str(path), skiprows=1)
        return data.ndim == 2 and data.shape[1] == 24 and data.shape[0] > 0
    except Exception:
        return False


def newest_valid_met_file(folder: Path):
    txts = sorted(folder.glob('*.txt'), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in txts:
        if is_valid_solweig_met(p):
            return p
    return None

# 1) Fetch ERA5 met if requested
if fetch_met:
    print('Attempting ERA5 download for Bonn using UMEP...')
    # QGIS Processing point parameters are most robust when passed as
    # "x,y [EPSG:xxxx]" strings.
    point_str = f'{center_x},{center_y} [EPSG:25832]'
    met_params = {
        'INPUT_POINT': point_str,
        'CRS': 'EPSG:25832',
        'DATEINISTART': start_date,
        'DATEINIEND': end_date,
        'DIAG_HEIGHT': 100.0,
        'OUTPUT_DIR': str(met_dir),
    }
    try:
        processing.run('umep:Meteorological Data: Download data (ERA5)', met_params)
        print('ERA5 download step completed.')
    except Exception as e:
        print(f'WARNING: ERA5 download failed with point string format: {e}')
        # Fallback for environments where the provider expects QgsPointXY.
        try:
            met_params['INPUT_POINT'] = QgsPointXY(center_x, center_y)
            processing.run('umep:Meteorological Data: Download data (ERA5)', met_params)
            print('ERA5 download step completed (QgsPointXY fallback).')
        except Exception as e2:
            print(f'WARNING: ERA5 download failed: {e2}')

# 2) Pick best met file
met_file = newest_valid_met_file(met_dir)
if met_file is None:
    raise FileNotFoundError(
        'No valid SOLWEIG met file found in Data/Bonn/met. '\
        'Expected a text file with 24 columns after header. '\
        'Set BONN_FETCH_MET=1 with internet/CDS credentials or place bonn_met.txt manually.'
    )

canonical_met = met_dir / 'bonn_met.txt'
if met_file != canonical_met:
    shutil.copy2(met_file, canonical_met)
    met_file = canonical_met

print(f'Using met file: {met_file}')
if use_lc:
    print(f'Using land cover: {lc_path}')
else:
    print('Land cover disabled')

# 3) Wall height + aspect
wall_params = {
    'INPUT': str(base / 'DSM_bonn.tif'),
    'INPUT_LIMIT': 3.0,
    'OUTPUT_HEIGHT': str(output / 'wall_height.tif'),
    'OUTPUT_ASPECT': str(output / 'wall_aspect.tif'),
}
print('Running UMEP Wall Height and Aspect...')
processing.run('umep:Urban Geometry: Wall Height and Aspect', wall_params)

# 4) SVF package
svf_params = {
    'INPUT_DSM': str(base / 'DSM_bonn.tif'),
    'INPUT_CDSM': str(base / 'CDSM_bonn.tif'),
    'TRANS_VEG': 3,
    'INPUT_TDSM': None,
    'INPUT_THEIGHT': 25.0,
    'ANISO': True,
    'KMEANS': True,
    'CLUSTERS': 5,
    'WALL_SCHEME': False,
    'INPUT_DEM': None,
    'INPUT_SVFHEIGHT': 1.0,
    'OUTPUT_DIR': str(svf_dir),
    'OUTPUT_FILE': str(svf_dir / 'svf_total.tif'),
}
print('Running UMEP Sky View Factor...')
processing.run('umep:Urban Geometry: Sky View Factor', svf_params)

# 5) SOLWEIG
solweig_params = {
    'INPUT_DSM': str(base / 'DSM_bonn.tif'),
    'INPUT_SVF': str(svf_dir / 'svfs.zip'),
    'INPUT_HEIGHT': str(output / 'wall_height.tif'),
    'INPUT_ASPECT': str(output / 'wall_aspect.tif'),
    'TRANS_VEG': 3,
    'LEAF_START': 97,
    'LEAF_END': 300,
    'CONIFER_TREES': False,
    'INPUT_CDSM': str(base / 'CDSM_bonn.tif'),
    'INPUT_TDSM': None,
    'INPUT_THEIGHT': 25,
    'INPUT_LC': str(lc_path) if use_lc else None,
    'USE_LC_BUILD': False,
    'INPUT_DEM': str(base / 'DEM_bonn.tif'),
    'SAVE_BUILD': False,
    'INPUT_ANISO': None,
    'INPUT_WALLSCHEME': None,
    'WALLTEMP_NETCDF': False,
    'WALL_TYPE': 0,
    'ALBEDO_WALLS': 0.2,
    'ALBEDO_GROUND': 0.15,
    'EMIS_WALLS': 0.9,
    'EMIS_GROUND': 0.95,
    'ABS_S': 0.7,
    'ABS_L': 0.95,
    'POSTURE': 0,
    'CYL': True,
    'INPUTMET': str(met_file),
    'ONLYGLOBAL': True,
    'UTC': 1,
    'WOI_FILE': None,
    'WOI_FIELD': None,
    'POI_FILE': None,
    'POI_FIELD': None,
    'AGE': 35,
    'ACTIVITY': 80,
    'CLO': 0.9,
    'WEIGHT': 75,
    'HEIGHT': 180,
    'SEX': 0,
    'SENSOR_HEIGHT': 10,
    'OUTPUT_TMRT': True,
    'OUTPUT_KDOWN': all_outputs,
    'OUTPUT_KUP': all_outputs,
    'OUTPUT_LDOWN': all_outputs,
    'OUTPUT_LUP': all_outputs,
    'OUTPUT_SH': all_outputs,
    'OUTPUT_TREEPLANTER': False,
    'OUTPUT_DIR': str(solweig_dir),
}
print('Running UMEP SOLWEIG for Bonn...')
result = processing.run('umep:Outdoor Thermal Comfort: SOLWEIG', solweig_params)
print('Done. Result keys:', sorted(result.keys()))
# QGIS/PyQt teardown can segfault in some environments after successful runs.
# Keep default as safe hard-exit once outputs are written.
if os.environ.get('BONN_SAFE_EXIT', '1') == '1':
    os._exit(0)
else:
    qgs.exitQgis()
