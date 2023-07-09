"""
 static test for PPP (BeiDou PPP)
"""
import matplotlib.pyplot as plt
import numpy as np

import cssrlib.gnss as gn
from cssrlib.gnss import ecef2pos, Nav
from cssrlib.gnss import time2gpst, time2doy, time2str, timediff, epoch2time
from cssrlib.gnss import rSigRnx
from cssrlib.gnss import sys2str
from cssrlib.peph import atxdec, searchpcv
from cssrlib.peph import peph
from cssrlib.cssr_bds import cssr_bds
from cssrlib.pppssr import rtkinit, ppppos, IT
from cssrlib.rinex import rnxdec
from binascii import unhexlify
import bitstruct.c as bs

# Start epoch and number of epochs
#
ep = [2023, 7, 8, 4, 0, 0]

time = epoch2time(ep)
year = ep[0]
doy = int(time2doy(time))
nep = 900

navfile = '../data/SEPT1890.23P'
#navfile = '../data/BRDC00IGS_R_20231890000_01D_MN.rnx'
obsfile = '../data/SEPT1890.23O'

file_bds = '../data/bdsb2b_189e.txt'
dtype = [('wn', 'int'), ('tow', 'int'), ('prn', 'int'),
         ('type', 'int'),('len', 'int'), ('nav', 'S124')]
v = np.genfromtxt(file_bds, dtype=dtype)

xyz_ref = [-3962108.673,   3381309.574,   3668678.638]
pos_ref = ecef2pos(xyz_ref)

# Define signals to be processed
#
sigs = [rSigRnx("GC1C"), rSigRnx("GC2W"),
        rSigRnx("GL1C"), rSigRnx("GL2W"),
        rSigRnx("GS1C"), rSigRnx("GS2W"),
        rSigRnx("CC1P"), rSigRnx("CC5P"),
        rSigRnx("CL1P"), rSigRnx("CL5P"),
        rSigRnx("CS1P"), rSigRnx("CS5P")]

atxfile = '../data/igs14.atx'

rnx = rnxdec()
rnx.setSignals(sigs)

nav = Nav()
orb = peph()

# Positioning mode
# 0:static, 1:kinematic
#
nav.pmode = 0
#nav.maxout = 100

# Decode RINEX NAV data
#
nav = rnx.decode_nav(navfile, nav)

cs = cssr_bds()
cs.mon_level = 2

# Load ANTEX data for satellites and stations
#
atx = atxdec()
atx.readpcv(atxfile)

# Set satelite antenna PCO/PCV data
#
nav.sat_ant = atx.pcvs

# Intialize data structures for results
#
t = np.zeros(nep)
tc = np.zeros(nep)
enu = np.ones((nep, 3))*np.nan
sol = np.zeros((nep, 4))
dop = np.zeros((nep, 4))
ztd = np.zeros((nep, 1))
smode = np.zeros(nep, dtype=int)

# Load RINEX OBS file header
#
if rnx.decode_obsh(obsfile) >= 0:

    if 'UNKNOWN' in rnx.ant or rnx.ant.strip() == '':
        rnx.ant = "{:16s}{:4s}".format("JAVRINGANT_DM", "SCIS")

    # Get equipment information
    #
    print("Receiver:", rnx.rcv)
    print("Antenna :", rnx.ant)
    print()

    if 'UNKNOWN' in rnx.ant or rnx.ant.strip() == "":
        print("ERROR: missing antenna type in RINEX OBS header!")

    # Set PCO/PCV information
    #
    nav.rcv_ant = searchpcv(atx.pcvr, rnx.ant,  rnx.ts)
    if nav.rcv_ant is None:
        print("ERROR: missing antenna type <{}> in ANTEX file!".format(rnx.ant))

    # Print available signals
    #
    print("Available signals")
    for sys, sigs in rnx.sig_map.items():
        txt = "{:7s} {}".format(sys2str(sys),
                                ' '.join([sig.str() for sig in sigs.values()]))
        print(txt)
    print()

    print("Selected signals")
    for sys, tmp in rnx.sig_tab.items():
        txt = "{:7s} ".format(sys2str(sys))
        for _, sigs in tmp.items():
            txt += "{} ".format(' '.join([sig.str() for sig in sigs]))
        print(txt)
    print()

    # Position
    #
    rr = rnx.pos
    rtkinit(nav, rnx.pos)
    pos = ecef2pos(rr)

    nav.monlevel = 1  # TODO: enabled for testing!
    prn_ref = 59
    mid_ = -1
    rec = []
    mid_decoded = []
    has_pages = np.zeros((255,53),dtype=int)
    # Loop over number of epoch from file start
    #
    for ne in range(nep):

        obs = rnx.decode_obs()
        week, tow = time2gpst(obs.t)
        cs.week = week
        cs.tow0 = tow//86400*86400

        # Set intial epoch
        #
        if ne == 0:
            t0 = nav.t = obs.t
            t0.time = t0.time//30*30
            nav.time_p = t0

        vi = v[(v['tow']==tow) & (v['prn']==prn_ref)]
        buff = unhexlify(vi['nav'][0])  

        #prn, rev = bs.unpack_from('u6u6',buff,0)
        cs.decode_cssr(buff,0)
     
        # Call PPP module with IGS products
        #
        if (cs.lc[0].cstat & 0xf) == 0xf:
            ppppos(nav, obs, cs = cs)

        # Save output
        #
        t[ne] = timediff(nav.t, t0)/60

        sol = nav.xa[0:3] if nav.smode == 4 else nav.x[0:3]
        enu[ne, :] = gn.ecef2enu(pos_ref, sol-xyz_ref)

        ztd[ne] = nav.xa[IT(nav.na)] if nav.smode == 4 else nav.x[IT(nav.na)]
        smode[ne] = nav.smode

        if False:
            print("{} {:14.4f} {:14.4f} {:14.4f} {:14.4f} {:14.4f} {:14.4f} {:2d}"
                  .format(time2str(obs.t),
                          sol[0], sol[1], sol[2],
                          enu[ne, 0], enu[ne, 1], enu[ne, 2],
                          smode[ne]))

    rnx.fobs.close()

fig_type = 1
ylim = 0.4

idx4 = np.where(smode == 4)[0]
idx5 = np.where(smode == 5)[0]
idx0 = np.where(smode == 0)[0]

fig = plt.figure(figsize=[7, 9])

if fig_type == 1:

    lbl_t = ['East [m]', 'North [m]', 'Up [m]']
    x_ticks = np.arange(0, nep/60+1, step=1)

    for k in range(3):
        plt.subplot(4, 1, k+1)
        plt.plot(t[idx0], enu[idx0, k], 'r.')
        plt.plot(t[idx5], enu[idx5, k], 'y.')
        plt.plot(t[idx4], enu[idx4, k], 'g.')

        plt.xticks(x_ticks)
        plt.ylabel(lbl_t[k])
        plt.grid()
        #plt.axis([0, ne, -ylim, ylim])

    plt.subplot(4, 1, 4)
    plt.plot(t[idx0], ztd[idx0]*1e2, 'r.', markersize=8, label='none')
    plt.plot(t[idx5], ztd[idx5]*1e2, 'y.', markersize=8, label='float')
    plt.plot(t[idx4], ztd[idx4]*1e2, 'g.', markersize=8, label='fix')
    plt.xticks(x_ticks)
    plt.ylabel('ZTD [cm]')
    plt.grid()
    plt.xlabel('Time [min]')
    plt.legend()

elif fig_type == 2:

    ax = fig.add_subplot(111)

    #plt.plot(enu[idx0, 0], enu[idx0, 1], 'r.', label='stdpos')
    plt.plot(enu[idx5, 0], enu[idx5, 1], 'y.', label='float')
    plt.plot(enu[idx4, 0], enu[idx4, 1], 'g.', label='fix')

    plt.xlabel('Easting [m]')
    plt.ylabel('Northing [m]')
    plt.grid()
    plt.axis('equal')
    plt.legend()
    #ax.set(xlim=(-ylim, ylim), ylim=(-ylim, ylim))

plotFileFormat = 'eps'
plotFileName = '.'.join(('test_ppphas', plotFileFormat))

plt.savefig(plotFileName, format=plotFileFormat, bbox_inches='tight')

# plt.show()