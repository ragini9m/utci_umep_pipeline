#!/usr/bin/env python3
import os
import sys
import shutil
from pathlib import Path

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

from qgis.core import QgsApplication

QgsApplication.setPrefixPath('/usr', True)
qgs = QgsApplication([], False)
qgs.initQgis()

import processing
from processing.core.Processing import Processing
Processing.initialize()

from processing_umep.processing_umep_provider import ProcessingUMEPProvider
umep_provider = ProcessingUMEPProvider()
QgsApplication.processingRegistry().addProvider(umep_provider)

base = Path(os.environ.get('BONN_INPUT_DIR', 'Data/Bonn/processed'))
output = Path('bonn_output')
output.mkdir(exist_ok=True)
svf_dir = output / 'svf'
svf_dir.mkdir(exist_ok=True)
solweig_dir = output / 'solweig'
solweig_dir.mkdir(exist_ok=True)

# Meteorology file preference:
# 1) user-provided Data/Bonn/met/bonn_met.txt
# 2) fallback tutorial forcing for pipeline testing only
met_preferred = Path('Data') / 'Bonn' / 'met' / 'bonn_met.txt'
met_fallback = Path('Data') / 'Goteborg_SWEREF99_1200' / 'gbg19970606_2015a.txt'
if met_preferred.exists():
    met_file = met_preferred
    print(f'Using Bonn met forcing: {met_file}')
else:
    met_file = met_fallback
    print(f'WARNING: Bonn met forcing not found, using fallback test forcing: {met_file}')

required = [base / 'DSM_bonn.tif', base / 'DEM_bonn.tif', base / 'CDSM_bonn.tif', met_file]
missing = [str(p) for p in required if not p.exists()]
if missing:
    raise FileNotFoundError('Missing required files:\n' + '\n'.join(missing))

# Step 1: Wall height + aspect
wall_params = {
    'INPUT': str(base / 'DSM_bonn.tif'),
    'INPUT_LIMIT': 3.0,
    'OUTPUT_HEIGHT': str(output / 'wall_height.tif'),
    'OUTPUT_ASPECT': str(output / 'wall_aspect.tif'),
}
print('Running UMEP Wall Height and Aspect...')
processing.run('umep:Urban Geometry: Wall Height and Aspect', wall_params)

# Step 2: SVF package
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

# Step 3: SOLWEIG
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
    'INPUT_LC': None,
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
    'OUTPUT_KDOWN': True,
    'OUTPUT_KUP': True,
    'OUTPUT_LDOWN': True,
    'OUTPUT_LUP': True,
    'OUTPUT_SH': True,
    'OUTPUT_TREEPLANTER': False,
    'OUTPUT_DIR': str(solweig_dir),
}
print('Running UMEP SOLWEIG for Bonn...')
result = processing.run('umep:Outdoor Thermal Comfort: SOLWEIG', solweig_params)
print('Done. Result keys:', sorted(result.keys()))

qgs.exitQgis()
