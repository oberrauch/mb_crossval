# -*- coding: utf-8 -*-
import warnings

warnings.filterwarnings("once", category=DeprecationWarning)  # noqa
import logging

import os
from glob import glob

# Libs
import numpy as np
import pandas as pd
import geopandas as gpd

# Local imports
from oggm import cfg, utils, tasks, workflow
from oggm.workflow import execute_entity_task
from oggm.core.massbalance import MultipleFlowlineMassBalance

import oggm_vas.core as vascaling

from mbcrossval import mbcfg

# Module logger
log = logging.getLogger(__name__)


def preprocessing(gdirs):
    # Prepro tasks
    task_list = [
        tasks.glacier_masks,
        # tasks.compute_centerlines,
        # tasks.initialize_flowlines,
        # tasks.catchment_area,
        # tasks.catchment_intersections,
        # tasks.catchment_width_geom,
        # tasks.catchment_width_correction,
    ]
    for task in task_list:
        execute_entity_task(task, gdirs)

    # Climate tasks
    execute_entity_task(tasks.process_histalp_data, gdirs)

    return gdirs


def calibration(gdirs, xval, major=0):
    # once for reference t_stars
    vascaling.compute_ref_t_stars(gdirs)
    execute_entity_task(vascaling.local_t_star, gdirs)

    full_ref_df = pd.read_csv(os.path.join(cfg.PATHS['working_dir'],
                                           'ref_tstars.csv'), index_col=0)
    out = execute_entity_task(quick_crossval_entity, gdirs,
                              full_ref_df=full_ref_df)

    # length of xval dict to get current position
    _x = len(xval)
    xval.loc[_x] = 0
    nans = np.array([])

    for col in xval.columns:
        if col == 'nans':
            continue
        values = np.array([])
        for glc in out:
            # xval.loc[_x, col] += glc[0][col]  # TODO
            values = np.append(values, glc[0][col])

            if not major:
                # store cross validated values
                for key in glc[1].keys():
                    if ('cv_' in key) or ('mu_star' in key) or \
                            ('mustar' in key):
                        full_ref_df.loc[glc[1]['rgi_id'], key] = glc[1][key]

        # sum of nans = number of failed glaciers
        nans = np.append(nans, np.isnan(values).sum())
        # calculate means of bias, rmse, ...
        xval.loc[_x, col] = np.nanmean(values)
    # calculate standard deviation quotient
    xval.loc[_x, 'std_quot'] = (xval.loc[_x, 'std_oggm'] /
                                xval.loc[_x, 'std_ref'])

    # treat and save nans:
    nans = nans[nans != len(gdirs)]
    if (nans == 0).all():
        xval.loc[_x, 'nans'] = 0
    elif nans[nans != 0].mean() == nans.max():
        xval.loc[_x, 'nans'] = nans.max()
    else:
        raise RuntimeError('something unexpected happened during nan counting')

    if not major:
        # get interpolated mu star
        out = execute_entity_task(interpolate_mu_star, gdirs,
                                  full_ref_df=full_ref_df)
        for glc in out:
            full_ref_df.loc[glc[0], 'interp_mustar'] = glc[1]
        # write crossvalidation if minor
        file = os.path.join(cfg.PATHS['working_dir'], 'crossval_tstars.csv')
        # sort first
        full_ref_df.sort_index(axis=1, inplace=True)
        full_ref_df.to_csv(file)
    return xval


def quick_crossval_entity(gdir, full_ref_df=None):
    tmpdf = pd.DataFrame([], columns=['std_oggm',
                                      'std_ref',
                                      'rmse',
                                      'core',
                                      'bias'])

    # the reference glaciers
    tmp_ref_df = full_ref_df.loc[full_ref_df.index != gdir.rgi_id]

    # before the cross-val store the info about "real" mustar
    ref_rdf = gdir.read_json('vascaling_mustar')

    vascaling.local_t_star(gdir, ref_df=tmp_ref_df)

    # read crossvalidated values
    cv_rdf = gdir.read_json('vascaling_mustar')

    # ----
    # --- MASS-BALANCE MODEL
    mb_mod = vascaling.VAScalingMassBalance(gdir)

    # Mass-balance timeseries, observed and simulated
    refmb = gdir.get_ref_mb_data().copy()
    min_hgt, max_hgt = vascaling.get_min_max_elevation(gdir)
    refmb['OGGM'] = mb_mod.get_specific_mb(min_hgt, max_hgt, year=refmb.index)

    # store single glacier results
    bias = refmb.OGGM.mean() - refmb.ANNUAL_BALANCE.mean()
    rmse = np.sqrt(np.mean(refmb.OGGM - refmb.ANNUAL_BALANCE) ** 2)
    rcor = np.corrcoef(refmb.OGGM, refmb.ANNUAL_BALANCE)[0, 1]

    ref_std = refmb.ANNUAL_BALANCE.std()

    # unclear how to treat this best
    if ref_std == 0:
        ref_std = refmb.OGGM.std()
        rcor = 1

    tmpdf.loc[len(tmpdf.index)] = {'std_oggm': refmb.OGGM.std(),
                                   'std_ref': ref_std,
                                   'bias': bias,
                                   'rmse': rmse,
                                   'core': rcor
                                   }

    # and store mean values
    out = {'prcpsf': cfg.PARAMS['prcp_scaling_factor'],
           'tliq': cfg.PARAMS['temp_all_liq'],
           'tmelt': cfg.PARAMS['temp_melt'],
           'tgrad': cfg.PARAMS['temp_default_gradient'],
           'std_oggm': tmpdf.std_oggm.values[0],
           'std_ref': tmpdf.std_ref.values[0],
           'std_quot': np.nan,
           'bias': tmpdf['bias'].mean(),
           'rmse': tmpdf['rmse'].mean(),
           'core': tmpdf['core'].mean()}

    # combine "real" mustar and crossvalidated mu_star
    for col in cv_rdf.keys():
        if 'rgi_id' in col:
            continue
        ref_rdf['cv_' + col] = cv_rdf[col]

    return [out, ref_rdf]


def interpolate_mu_star(gdir, full_ref_df=None):
    # make it an entity task
    # ----
    # Interpolated mu_star
    # ----
    tmp_ref_df = full_ref_df.loc[full_ref_df.index != gdir.rgi_id]
    glc = full_ref_df.loc[full_ref_df.index == gdir.rgi_id]
    # Compute the distance
    distances = utils.haversine(glc.lon.values[0], glc.lat.values[0],
                                tmp_ref_df.lon, tmp_ref_df.lat)

    # Take the 10 closests
    aso = np.argsort(distances)[0:9]
    amin = tmp_ref_df.iloc[aso]
    distances = distances[aso] ** 2
    interp = np.average(amin.mu_star,
                        weights=1. / distances)

    return [gdir.rgi_id, interp]


def initialization_selection():
    # -------------
    # Initialization
    # -------------
    cfg.initialize()

    # working directories
    cfg.PATHS['working_dir'] = mbcfg.PATHS['working_dir']

    cfg.PATHS['rgi_version'] = mbcfg.PARAMS['rgi_version']

    # We are running the calibration ourselves
    cfg.PARAMS['run_mb_calibration'] = True

    # No need for intersects since this has an effect on the inversion only
    cfg.PARAMS['use_intersects'] = False

    # Use multiprocessing?
    cfg.PARAMS['use_multiprocessing'] = True

    # Set to True for operational runs
    # maybe also here?
    cfg.PARAMS['continue_on_error'] = True

    # set negative flux filtering to false. should be standard soon
    cfg.PARAMS['filter_for_neg_flux'] = False

    # correct negative fluxes with flowline mus
    cfg.PARAMS['correct_for_neg_flux'] = True

    # use glacierwiede mu_star in order to finde t_star: it's faster!
    cfg.PARAMS['tstar_search_glacierwide'] = True

    # Pre-download other files which will be needed later
    # _ = cru.get_cru_file(var='tmp')
    # _ = cru.get_cru_file(var='pre')
    rgi_dir = utils.get_rgi_dir(version=cfg.PATHS['rgi_version'])

    # Get the reference glacier ids (they are different for each RGI version)
    df, _ = utils.get_wgms_files()
    rids = df['RGI{}0_ID'.format(cfg.PATHS['rgi_version'])]

    # Make a new dataframe with those (this takes a while)
    rgidf = []
    for reg in df['RGI_REG'].unique():
        if reg == '19':
            continue  # we have no climate data in Antarctica
        if mbcfg.PARAMS['region'] is not None \
                and reg != mbcfg.PARAMS['region']:
            continue

        fn = '*' + reg + '_rgi{}0_*.shp'.format(cfg.PATHS['rgi_version'])
        fs = list(sorted(glob(os.path.join(rgi_dir, '*', fn))))[0]
        sh = gpd.read_file(fs)
        rgidf.append(sh.loc[sh.RGIId.isin(rids)])
    rgidf = pd.concat(rgidf)
    rgidf.crs = sh.crs  # for geolocalisation

    # reduce Europe to Histalp area (exclude Pyrenees, etc...)
    rgidf = rgidf.loc[(rgidf.CenLon >= 4) &
                      (rgidf.CenLon < 20) &
                      (rgidf.CenLat >= 43) &
                      (rgidf.CenLat < 47)]

    # and set standard histalp values
    cfg.PARAMS['prcp_scaling_factor'] = 1.75
    cfg.PARAMS['temp_all_liq'] = 2.0
    cfg.PARAMS['temp_melt'] = -1.75
    cfg.PARAMS['temp_default_gradient'] = -0.0065

    # We have to check which of them actually have enough mb data.
    # Let OGGM do it:
    gdirs = workflow.init_glacier_regions(rgidf)
    # We need to know which period we have data for
    cfg.PARAMS['baseline_climate'] = 'HISTALP'
    execute_entity_task(tasks.process_histalp_data, gdirs)

    gdirs = utils.get_ref_mb_glaciers(gdirs)
    # Keep only these
    rgidf = rgidf.loc[rgidf.RGIId.isin([g.rgi_id for g in gdirs])]

    # Save
    rgidf.to_file(os.path.join(cfg.PATHS['working_dir'],
                               'mb_ref_glaciers.shp'))

    # Sort for more efficient parallel computing
    rgidf = rgidf.sort_values('Area', ascending=False)

    # Go - initialize working directories
    gdirs = workflow.init_glacier_regions(rgidf, reset=True, force=True)

    return gdirs


def minor_xval_statistics(gdirs):
    # initialize the pandas dataframes

    # to store mass balances of every glacier
    mbdf = pd.DataFrame([], index=np.arange(1850, 2050))

    # Cross-validation
    file = os.path.join(cfg.PATHS['working_dir'], 'crossval_tstars.csv')
    cvdf = pd.read_csv(file, index_col=0)

    # dataframe output
    xval = pd.DataFrame([], columns=['RGIId',
                                     'Name',
                                     'tstar_bias',
                                     'xval_bias',
                                     'interp_bias',
                                     'mustar',
                                     'tstar',
                                     'xval_mustar',
                                     'xval_tstar',
                                     'interp_mustar'])

    for gd in gdirs:
        t_cvdf = cvdf.loc[gd.rgi_id]
        # heights, widths = gd.get_inversion_flowline_hw()

        # Observed mass-blance
        refmb = gd.get_ref_mb_data().copy()

        # Mass-balance model with cross-validated parameters instead
        # use the cross validated flowline mustars:

        mb_mod = vascaling.VAScalingMassBalance(gd, mu_star=t_cvdf.cv_mu_star,
                                                bias=t_cvdf.cv_bias)
        min_hgt, max_hgt = vascaling.get_min_max_elevation(gd)
        refmb['OGGM_cv'] = mb_mod.get_specific_mb(min_hgt, max_hgt,
                                                  year=refmb.index)
        # Compare their standard deviation
        std_ref = refmb.ANNUAL_BALANCE.std()
        rcor = np.corrcoef(refmb.OGGM_cv, refmb.ANNUAL_BALANCE)[0, 1]
        if std_ref == 0:
            # I think that such a thing happens with some geodetic values
            std_ref = refmb.OGGM_cv.std()
            rcor = 1
        # Store the scores
        cvdf.loc[gd.rgi_id, 'CV_MB_BIAS'] = (refmb.OGGM_cv.mean() -
                                             refmb.ANNUAL_BALANCE.mean())
        cvdf.loc[gd.rgi_id, 'CV_MB_SIGMA_BIAS'] = (refmb.OGGM_cv.std() /
                                                   std_ref)
        cvdf.loc[gd.rgi_id, 'CV_MB_COR'] = rcor

        # Mass-balance model with interpolated mu_star
        mb_mod = vascaling.VAScalingMassBalance(gd,
                                                mu_star=t_cvdf.interp_mustar,
                                                bias=t_cvdf.cv_bias)
        min_hgt, max_hgt = vascaling.get_min_max_elevation(gd)
        refmb['OGGM_mu_interp'] = mb_mod.get_specific_mb(min_hgt, max_hgt,
                                                         year=refmb.index)
        cvdf.loc[gd.rgi_id, 'INTERP_MB_BIAS'] = (refmb.OGGM_mu_interp.mean() -
                                                 refmb.ANNUAL_BALANCE.mean())

        # Mass-balance model with best guess tstar

        mb_mod = vascaling.VAScalingMassBalance(gd, mu_star=t_cvdf.mu_star,
                                                bias=t_cvdf.bias)
        min_hgt, max_hgt = vascaling.get_min_max_elevation(gd)
        refmb['OGGM_tstar'] = mb_mod.get_specific_mb(min_hgt, max_hgt,
                                                     year=refmb.index)
        cvdf.loc[gd.rgi_id, 'tstar_MB_BIAS'] = (refmb.OGGM_tstar.mean() -
                                                refmb.ANNUAL_BALANCE.mean())

        # Pandas DataFrame Output
        #
        # 1. statistics
        tbias = cvdf.loc[gd.rgi_id, 'tstar_MB_BIAS']
        xbias = cvdf.loc[gd.rgi_id, 'CV_MB_BIAS']
        ibias = cvdf.loc[gd.rgi_id, 'INTERP_MB_BIAS']
        xval = xval.append({'Name': gd.name,
                            'RGIId': gd.rgi_id,
                            'tstar_bias': tbias,
                            'xval_bias': xbias,
                            'interp_bias': ibias,
                            # TODO wie mach ich das mit den Flowline Mus hier?
                            'mustar': t_cvdf.mu_star,
                            'tstar': t_cvdf.tstar,
                            'xval_mustar': t_cvdf.cv_mu_star,
                            'xval_tstar': t_cvdf.cv_t_star,
                            'interp_mustar': t_cvdf.interp_mustar},
                           ignore_index=True)

        #
        # 2. mass balance timeseries
        mbarray = np.dstack((refmb.ANNUAL_BALANCE,
                             refmb.OGGM_tstar,
                             refmb.OGGM_cv)).squeeze()

        mbdf_add = pd.DataFrame(mbarray,
                                columns=[[gd.rgi_id, gd.rgi_id, gd.rgi_id],
                                         ['measured',
                                          'calibrated',
                                          'crossvalidated']],
                                index=refmb.index)
        mbdf = pd.concat([mbdf, mbdf_add], axis=1)

    mbdf.columns = pd.MultiIndex.from_tuples(mbdf.columns)

    mbdf = mbdf.dropna(how='all')

    xval.index = xval.RGIId

    return xval, mbdf
