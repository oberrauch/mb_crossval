# -*- coding: utf-8 -*-
# Plot
import matplotlib.pyplot as plt

import os

# Libs
import numpy as np
import pandas as pd
import pickle

from mbcrossval import mbcfg


def crossval_boxplot(file, plotdir):
    # load pickle file
    xvaldict = pickle.load(open(file, 'rb'))
    xval = xvaldict['statistic'].astype(float)

    try:
        glcs = xvaldict['glaciers']
    except KeyError:
        # Legacy
        glcs = None

    # for convenience
    xval.tgrad *= 1000
    xval.tgrad = np.round(xval.tgrad, decimals=1)

    # some plotting stuff:
    labels = {'prcpsf': 'Precipitation Factor',
              'tliq': 'T liquid precipitation [deg C]',
              'tmelt': 'Melt temperature [deg C]',
              'tgrad': 'Temperature lapse rate [K/km]'}
    # some plotting stuff:
    title = {'prcpsf': 'Precipitation Factor',
             'tliq': 'Liquid precipitation temperature',
             'tmelt': 'Melt temperature',
             'tgrad': 'Temperature lapse rate'}

    if 'histalp' in os.path.basename(file):
        allvar = {'prcpsf': 1.75, 'tliq': 2.0, 'tmelt': -1.75, 'tgrad': -6.5}
    else:
        allvar = {'prcpsf': 2.5, 'tliq': 2.0, 'tmelt': -1.0, 'tgrad': -6.5}

    for var in allvar.keys():
        f, ((ax0, ax1), (ax2, ax3)) = plt.subplots(2, 2, figsize=(13, 7))

        # find the entries with the standard values
        var0 = allvar.copy()
        del var0[var]
        idx = list(var0.keys())

        base = xval.loc[np.isclose(xval[idx[0]], var0[idx[0]]) &
                        np.isclose(xval[idx[1]], var0[idx[1]]) &
                        np.isclose(xval[idx[2]], var0[idx[2]])]

        try:
            nans = xval.groupby(by=var).sum()['nans']
        except KeyError:
            # Legacy
            nans = None

        # RMSE
        xval.boxplot(column='rmse', by=var, ax=ax0, grid=False,
                     positions=base[var], widths=0.2, showfliers=False)
        ax0.plot(base[var].values, base['rmse'].values, 'or')
        ax0.set_ylabel('mean rmse')
        ax0.set_xlabel('')
        ax0.set_title('')
        ax0.set_ylim((200, 800))
        ax0.plot((allvar[var], allvar[var]), ax0.get_ylim(), 'k-', linewidth=1)

        if nans is not None:
            ax0b = ax0.twiny()
            ax0b.set_xlim(ax0.get_xlim())
            ax0b.set_xticks(nans.index.values)
            xtl = ['# %d' % i for i in nans]
            ax0b.set_xticklabels(xtl)

        # BIAS
        xval.boxplot(column='bias', by=var, ax=ax1, grid=False,
                     positions=base[var], widths=0.2, showfliers=False)
        ax1.plot(base[var].values, base['bias'].values, 'or')
        ax1.plot(ax1.get_xlim(), (0.0, 0.0), 'k-', linewidth=1)
        ax1.set_ylabel('mean bias')
        ax1.set_xlabel('')
        ax1.set_title('')
        ax1.set_ylim((-400, 100))
        ax1.plot((allvar[var], allvar[var]), ax1.get_ylim(), 'k-', linewidth=1)

        if nans is not None:
            ax1b = ax1.twiny()
            ax1b.set_xlim(ax1.get_xlim())
            ax1b.set_xticks(nans.index.values)
            xtl = ['# %d' % i for i in nans]
            ax1b.set_xticklabels(xtl)

        # STD quotient
        xval.boxplot(column='std_quot', by=var, ax=ax2, grid=False,
                     positions=base[var], widths=0.2, showfliers=False)
        ax2.plot(base[var].values, base['std_quot'].values, 'or')
        ax2.plot(ax2.get_xlim(), (1.0, 1.0), 'k-', linewidth=1)
        ax2.set_xlabel(labels[var])
        ax2.set_ylabel('mean std quotient')
        ax2.set_title('')
        ax2.set_ylim((0, 3))
        ax2.plot((allvar[var], allvar[var]), ax2.get_ylim(), 'k-', linewidth=1)

        if nans is not None:
            ax2b = ax2.twiny()
            ax2b.set_xlim(ax2.get_xlim())
            ax2b.set_xticks(nans.index.values)
            xtl = ['# %d' % i for i in nans]
            ax2b.set_xticklabels(xtl)

        # CORE
        xval.boxplot(column='core', by=var, ax=ax3, grid=False,
                     positions=base[var], widths=0.2, showfliers=False)
        ax3.plot(base[var].values, base['core'].values, 'or')
        ax3.set_xlabel(labels[var])
        ax3.set_ylabel('mean correlation')
        ax3.set_title('')
        ax3.set_ylim((0.55, 0.65))
        ax3.plot((allvar[var], allvar[var]), ax3.get_ylim(), 'k-', linewidth=1)

        if nans is not None:
            ax3b = ax3.twiny()
            ax3b.set_xlim(ax3.get_xlim())
            ax3b.set_xticks(nans.index.values)
            xtl = ['# %d' % i for i in nans]
            ax3b.set_xticklabels(xtl)

        # title stuff
        maintitle = 'Crossvalidation results with respect to %s' % title[var]
        if nans is not None:
            maintitle = maintitle + '  (%d reference glaciers)' % glcs

            rmtxt = ("'# x': number of removed data points (from a total of "
                     "%d data points per %s value)"
                     % (len(xval.groupby(idx))*glcs, title[var]))
            plt.text(x=0.5, y=0.92, s=rmtxt, fontsize=9, ha="center",
                     transform=f.transFigure)

        f.suptitle('')

        plt.text(x=0.5, y=0.96, s=maintitle, fontsize=14, ha="center",
                 transform=f.transFigure)

        # f.tight_layout(pad=0.5, w_pad=2.0, h_pad=2.0, rect=[0, 0.01, 1, 0.90])
        plotname = os.path.join(plotdir, '%s_crossval_box.png' % var)
        f.savefig(plotname, format='png')
        plt.close(f)


def crossval_timeseries(file, plotdir):
    # load pickle file
    xvaldict = pickle.load(open(file, 'rb'))
    data = xvaldict['massbalance']
    # time series plots of mass balance

    # reindex for plotting
    reind = pd.Index(np.arange(data.index[0], data.index[-1]+1))

    for gd in data.columns.levels[0]:
        f, ax1 = plt.subplots(1, 1, figsize=(12, 5), sharey=True)

        ax1.plot(data[gd].measured.reindex(reind), 'ko-', linewidth=3,
                 label='Measured annual mass balance',
                 color='xkcd:charcoal')
        ax1.plot(data[gd].calibrated.reindex(reind), 'go-', linewidth=3,
                 label='OGGM: Calibrated t_star',
                 color='xkcd:bluish')
        ax1.plot(data[gd].crossvalidated.reindex(reind), 'ro-', linewidth=3,
                 label='OGGM: Crossvalidated t_star',
                 color='xkcd:reddish')
        ax1.set_xlabel('Years')
        ax1.set_ylabel('Specific mass-balance (mm w.e.)')
        ax1.legend(loc='best')

        name = xvaldict['per_glacier'].loc[gd].Name

        if name == '':
            ax1.set_title(gd)
        else:
            ax1.set_title('%s (%s)' % (gd, name))

        ax1.grid(True)
        f.tight_layout()
        plotname = os.path.join(plotdir, '%s.png' % gd)
        f.savefig(plotname, format='png')
        plt.close(f)


def crossval_histogram(file, plotdir):
    # histogramplot of the crossvalidation. compare Marzeion 2012, Figure 3
    # load pickle file
    xvaldict = pickle.load(open(file, 'rb'))
    data = xvaldict['per_glacier']

    # Marzeion et al Figure 3
    f, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5), sharey=True)
    bins = np.arange(20) * 400 - 3800
    data['xval_bias'].plot(ax=ax1, kind='hist', bins=bins,
                           color='C3', label='')
    ax1.vlines(data['xval_bias'].mean(), 0, 120,
               linestyles='--', label='Mean')
    ax1.vlines(data['xval_bias'].quantile(), 0, 120, label='Median')
    ax1.vlines(data['xval_bias'].quantile([0.05, 0.95]), 0, 120,
               color='grey',
               label='5% and 95%\npercentiles')
    ax1.text(0.01, 0.99, 'N = {}'.format(len(data)),
             horizontalalignment='left',
             verticalalignment='top',
             transform=ax1.transAxes)

    ax1.set_ylim(0, 120)
    ax1.set_ylabel('N Glaciers')
    ax1.set_xlabel('Mass-balance error (mm w.e. yr$^{-1}$)')
    ax1.legend(loc='best')
    ax1.set_title('Cross validated t_star')
    data['interp_bias'].plot(ax=ax2, kind='hist', bins=bins, color='C0')
    ax2.vlines(data['interp_bias'].mean(), 0, 120, linestyles='--')
    ax2.vlines(data['interp_bias'].quantile(), 0, 120)
    ax2.vlines(data['interp_bias'].quantile([0.05, 0.95]), 0, 120,
               color='grey')
    ax2.set_xlabel('Mass-balance error (mm w.e. yr$^{-1}$)')
    ax2.set_title('Interpolated mu_star')
    plotname = os.path.join(plotdir, 'mb_histogram.png')
    plt.tight_layout()
    plt.savefig(plotname, format='png')
    plt.close(f)
