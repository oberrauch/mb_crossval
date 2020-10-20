# -*- coding: utf-8 -*-
import warnings
warnings.filterwarnings("once", category=DeprecationWarning)  # noqa
import os
import argparse

# Local imports
from oggm import utils
from mbcrossval.run import run_main
from mbcrossval import mbcfg


def main():
    # define paths since call from terminal is not yet supported
    storage = './data/xval'
    webroot = './data/xval/http/'
    workdir = './working_directories/xval'
    
    # get paths from environment variables (for run on cluster)
    # storage = os.environ["STORAGE"]
    # webroot = os.environ["WEBROOT"]
    # workdir = os.environ["WORKDIR"]

    # define other parameters since call from terminal is not yet supported
    defaultcfg = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              'defaultconfig.cfg')
    config = defaultcfg

    histalp = True
    extended = True

    # run configuration file
    mbcfg.initialize(config)

    # HISTALP
    mbcfg.PARAMS['oggmversion'] = mbcfg.PARAMS['oggmversion'] + '-histalp'

    # Major crossvalidation
    mbcfg.PARAMS['run_major_crossval'] = extended

    # Working directory
    mbcfg.PATHS['working_dir'] = os.path.abspath(workdir)
    utils.mkdir(mbcfg.PATHS['working_dir'])

    # Storage directory
    mbcfg.PATHS['storage_dir'] = os.path.abspath(storage)
    utils.mkdir(mbcfg.PATHS['storage_dir'])

    # Website root directory
    mbcfg.PATHS['webroot'] = os.path.abspath(webroot)
    utils.mkdir(mbcfg.PATHS['webroot'])

    # Plotdir
    mbcfg.PATHS['plotdir'] = os.path.join(mbcfg.PATHS['webroot'],
                                          mbcfg.PARAMS['oggmversion'],
                                          'plots')
    utils.mkdir(mbcfg.PATHS['plotdir'])

    run_main()


if __name__ == '__main__':
    main()
