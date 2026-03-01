#!/usr/bin/env python3
import os
import sys
import shutil
from pathlib import Path

# Ensure all runtime caches/settings are written under this workspace.
workspace = Path(__file__).resolve().parent
os.environ['XDG_DATA_HOME'] = str(workspace / '.xdg_data')
os.environ['XDG_CONFIG_HOME'] = str(workspace / '.xdg_config')
os.environ['NUMBA_CACHE_DIR'] = str(workspace / '.numba_cache')
(workspace / '.xdg_data').mkdir(parents=True, exist_ok=True)
(workspace / '.xdg_config').mkdir(parents=True, exist_ok=True)
(workspace / '.numba_cache').mkdir(parents=True, exist_ok=True)

# Use a writable local copy of the UMEP plugin so temp files can be created.
source_umep = Path('/home/ginira/.local/share/QGIS/QGIS3/profiles/default/python/plugins/processing_umep')
local_plugins = workspace / '.qgis_plugins'
local_umep = local_plugins / 'processing_umep'
local_plugins.mkdir(parents=True, exist_ok=True)
if not local_umep.exists():
    shutil.copytree(source_umep, local_umep)

# Make QGIS and plugin modules importable in this environment.
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

base = Path('Data') / 'Goteborg_SWEREF99_1200'
output = Path('tutorial_output')
output.mkdir(exist_ok=True)
svf_dir = output / 'svf'
svf_dir.mkdir(exist_ok=True)
solweig_dir = output / 'solweig'
solweig_dir.mkdir(exist_ok=True)

# Step 1: Wall height and wall aspect (required by SOLWEIG v2025a)
wall_params = {
    'INPUT': str(base / 'DSM_KRbig.tif'),
    'INPUT_LIMIT': 3.0,
    'OUTPUT_HEIGHT': str(output / 'wall_height.tif'),
    'OUTPUT_ASPECT': str(output / 'wall_aspect.tif'),
}
print('Running UMEP Wall Height and Aspect...')
processing.run('umep:Urban Geometry: Wall Height and Aspect', wall_params)

# Step 2: Sky View Factor package (creates svfs.zip required by SOLWEIG v2025a)
svf_params = {
    'INPUT_DSM': str(base / 'DSM_KRbig.tif'),
    'INPUT_CDSM': str(base / 'CDSM_KRbig.asc'),
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

# Step 3: SOLWEIG (tutorial workflow, adapted to UMEP v2025a parameters)
params = {
    'INPUT_DSM': str(base / 'DSM_KRbig.tif'),
    'INPUT_SVF': str(svf_dir / 'svfs.zip'),
    'INPUT_HEIGHT': str(output / 'wall_height.tif'),
    'INPUT_ASPECT': str(output / 'wall_aspect.tif'),
    'TRANS_VEG': 3,
    'LEAF_START': 97,
    'LEAF_END': 300,
    'CONIFER_TREES': False,
    'INPUT_CDSM': str(base / 'CDSM_KRbig.asc'),
    'INPUT_TDSM': None,
    'INPUT_THEIGHT': 25,
    'INPUT_LC': str(base / 'landcover.tif'),
    'USE_LC_BUILD': False,
    'INPUT_DEM': str(base / 'DEM_KRbig.tif'),
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
    'INPUTMET': str(base / 'gbg19970606_2015a.txt'),
    'ONLYGLOBAL': True,
    'UTC': 0,
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

print('Running UMEP SOLWEIG with:')
for k, v in params.items():
    if k.startswith('OUTPUT_') or k.startswith('INPUT_'):
        print(f'  {k}: {v}')

result = processing.run('umep:Outdoor Thermal Comfort: SOLWEIG', params)
print('Done. Result keys:', sorted(result.keys()))

qgs.exitQgis()
