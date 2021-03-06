#!/usr/bin/env python

# Copyright (c) 2014-2018 Michael Hirsch, Ph.D.
#
# Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:
# 1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""
Input/output: default units are METERS and DEGREES.
boolean deg=True means degrees

For most functions you can input Numpy arrays of any shape, except as noted in the functions

see tests/Test.py for example uses.
"""
from __future__ import division
from copy import deepcopy
from six import string_types,PY2
from datetime import datetime
try:
    import numpy
    from numpy import sin, cos, tan, sqrt, radians, arctan2, hypot, degrees
except ImportError:
    numpy = None
    from math import sin, cos, tan, sqrt, radians, hypot, degrees
    from math import atan2 as arctan2
try:
    from astropy.time import Time
    from astropy import units as u
    from astropy.coordinates import Angle,SkyCoord, EarthLocation, AltAz, ICRS
except ImportError:
    Time = None
#
from .vallado import vazel2radec, vradec2azel
from .timeconv import str2dt


class EarthEllipsoid:
    """generate reference ellipsoid"""
    def __init__(self,model='wgs84'):
        if model == 'wgs84':
            """https://en.wikipedia.org/wiki/World_Geodetic_System#WGS84"""
            self.a = 6378137.  # semi-major axis [m]
            self.f = 1 / 298.2572235630  # flattening
            self.b = self.a * (1 - self.f)  # semi-minor axis
        elif model=='grs80':
            """https://en.wikipedia.org/wiki/GRS_80"""
            self.a = 6378137.  # semi-major axis [m]
            self.f = 1 / 298.257222100882711243  # flattening
            self.b = self.a * (1 - self.f)  # semi-minor axis


#%% to AER (azimuth, elevation, range)
def ecef2aer(x, y, z, lat0, lon0, h0, ell=None, deg=True):
    """
    Observer => Point

    input:
    -----
    x,y,z  [meters] target ECEF location                             [0,Infinity)
    lat0, lon0 (degrees/radians)  Observer coordinates on ellipsoid  [-90,90],[-180,180]
    h0     [meters]                observer altitude                 [0,Infinity)
    ell    reference ellipsoid
    deg    degrees input/output  (False: radians in/out)

    output: AER
    ------
    azimuth, elevation (degrees/radians)                             [0,360),[0,90]
    slant range [meters]                                             [0,Infinity)
    """
    xEast, yNorth, zUp = ecef2enu(x, y, z, lat0, lon0, h0, ell, deg=deg)

    return enu2aer(xEast, yNorth, zUp, deg=deg)


def eci2aer(eci, lat0, lon0, h0, t):
    """
    Observer => Point

    input
    -----
    eci [meters] Nx3 target ECI location (x,y,z)                    [0,Infinity)
    lat0, lon0 (degrees/radians)  Observer coordinates on ellipsoid [-90,90],[-180,180]
    h0     [meters]                observer altitude                [0,Infinity)
    t  time (datetime.datetime)   time of obsevation (UTC)


    output: AER
    ------
    azimuth, elevation (degrees/radians)                             [0,360),[0,90]
    slant range [meters]                                             [0,Infinity)
    """
    ecef = eci2ecef(eci, t)

    return ecef2aer(ecef[:, 0], ecef[:, 1], ecef[:, 2], lat0, lon0, h0)


def enu2aer(e, n, u, deg=True):
    """
    Observer => Point

    input
    -----
    e,n,u  [meters]  East, north, up                                [0,Infinity)
    deg    degrees input/output  (False: radians in/out)

    output: AER
    ------
    azimuth, elevation (degrees/radians)                             [0,360),[0,90]
    slant range [meters]                                             [0,Infinity)
    """
    r = hypot(e, n)
    slantRange = hypot(r, u)
    elev = arctan2(u, r)
    az =  arctan2(e, n) % (2 * arctan2(0, -1))
    if deg:
        return degrees(az), degrees(elev), slantRange
    else:
        return az, elev, slantRange  # radians


def geodetic2aer(lat, lon, h, lat0, lon0, h0, ell=None, deg=True):
    """
    Observer => Point

    input:
    -----
    Target:   lat, lon, h (altitude, meters)
    Observer: lat0, lon0, h0 (altitude, meters)
    ell    reference ellipsoid
    deg    degrees input/output  (False: radians in/out)

    output: AER
    ------
    azimuth, elevation (degrees/radians)
    slant range [meters]
    """
    e, n, u = geodetic2enu(lat, lon, h, lat0, lon0, h0, ell, deg=deg)

    return enu2aer(e, n, u, deg=deg)


def ned2aer(n, e, d, deg=True):
    """
    Observer => Point

    input
    -----
    n,e,d  [meters]  North,east, down                                [0,Infinity)
    deg    degrees input/output  (False: radians in/out)

    output: AER
    ------
    azimuth, elevation (degrees/radians)                             [0,360),[0,90]
    slant range [meters]                                             [0,Infinity)
    """
    return enu2aer(e, n, -d, deg=deg)

#%% to ECEF
def aer2ecef(az, el, srange, lat0, lon0, alt0, ell=None, deg=True):
    """
    convert target azimuth, elevation, range (meters) from observer at lat0,lon0,alt0 to ECEF coordinates.

     Input:
     -----
    azimuth, elevation (degrees/radians)                             [0,360),[0,90]
    slant range [meters]                                             [0,Infinity)
    Observer: lat0, lon0, h0 (altitude, meters)
    ell    reference ellipsoid
    deg    degrees input/output  (False: radians in/out)

     output: ECEF x,y,z  [meters]

    if you specify NaN for srange, return value z will be NaN
    """
    # Origin of the local system in geocentric coordinates.
    x0, y0, z0 = geodetic2ecef(lat0, lon0, alt0, ell, deg=deg)
    # Convert Local Spherical AER to ENU
    e1, n1, u1 = aer2enu(az, el, srange, deg=deg)
    # Rotating ENU to ECEF
    dx, dy, dz = _enu2uvw(e1, n1, u1, lat0, lon0, deg=deg)
    # Origin + offset from origin equals position in ECEF
    return x0 + dx, y0 + dy, z0 + dz


def eci2ecef(eci, t):
    """
     Observer => Point

    input
    -----
    eci [meters] Nx3 target ECI location (x,y,z)                    [0,Infinity)
    t  time (datetime.datetime)   time of obsevation (UTC)

    output
    ------
    x,y,z  [meters] target ECEF location                             [0,Infinity)
    """
    if numpy is None or Time is None:
        raise ImportError('eci2ecef requires Numpy and AstroPy')

    t = numpy.atleast_1d(t)
    if isinstance(t[0], string_types): #don't just ram in in case it's float
        t = str2dt(t)

    if isinstance(t[0], datetime):
        gst = Time(t).sidereal_time('apparent', 'greenwich').radian
    elif isinstance(t[0],float):
        gst = t
    else:
        raise TypeError('eci2ecef: time must be datetime or radian float')

    assert isinstance(gst[0], float)  # must be in radians!

    eci = numpy.atleast_2d(eci)
    N, trip = eci.shape
    if eci.ndim > 2 or trip != 3:
        raise ValueError('eci triplets must be shape (N,3)')
    """ported from:
    https://github.com/dinkelk/astrodynamics/blob/master/rot3.m
    """
    ecef = numpy.empty_like(eci)

    for i in range(N):
        #ecef[i, :] = _rottrip(gst[i]) @ eci[i, :]
        ecef[i, :] = _rottrip(gst[i]).dot(eci[i, :])

    return ecef


def enu2ecef(e1, n1, u1, lat0, lon0, h0, ell=None, deg=True):
    """
    Observer => Point

    inputs:
     e1, n1, u1 (meters)   east, north, up
     observer: lat0, lon0, h0 (degrees/radians,degrees/radians, meters)
    ell    reference ellipsoid
    deg    degrees input/output  (False: radians in/out)


    output
    ------
    x,y,z  [meters] target ECEF location                         [0,Infinity)
    """
    x0, y0, z0 = geodetic2ecef(lat0, lon0, h0, ell, deg=deg)
    dx, dy, dz = _enu2uvw(e1, n1, u1, lat0, lon0, deg=deg)

    return x0 + dx, y0 + dy, z0 + dz


def geodetic2ecef(lat, lon, alt, ell=None, deg=True):
    """
    Observer => Point

    input:
    -----
    Target:   lat, lon, h (altitude, meters)
    Observer: lat0, lon0, h0 (altitude, meters)
    ell    reference ellipsoid
    deg    degrees input/output  (False: radians in/out)

    output: ECEF x,y,z (meters)
    """
    if ell is None:
        ell = EarthEllipsoid()

    if deg:
        lat = radians(lat)
        lon = radians(lon)
    # radius of curvature of the prime vertical section
    N = get_radius_normal(lat, ell)
    # Compute cartesian (geocentric) coordinates given  (curvilinear) geodetic
    # coordinates.
    x = (N + alt) * cos(lat) * cos(lon)
    y = (N + alt) * cos(lat) * sin(lon)
    z = (N * (ell.b / ell.a)**2 + alt) * sin(lat)

    return x, y, z


def ned2ecef(n, e, d, lat0, lon0, h0, ell=None, deg=True):
    """
    Observer => Point

    input
    -----
    n,e,d  [meters]  North,east, down                                [0,Infinity)
    Observer: lat0, lon0, h0 (altitude, meters)
    ell    reference ellipsoid
    deg    degrees input/output  (False: radians in/out)

    output:
    ------
    ECEF  x,y,z  (meters)
    """
    return enu2ecef(e, n, -d, lat0, lon0, h0, ell, deg=deg)

#%% to ECI
def aer2eci(az, el, srange, lat0, lon0, h0, t, ell=None, deg=True):
    """

    input
    -----
    azimuth, elevation (degrees/radians)                             [0,360),[0,90]
    slant range [meters]                                             [0,Infinity)
    Observer: lat0, lon0, h0 (altitude, meters)
    ell    reference ellipsoid
    deg    degrees input/output  (False: radians in/out)
    t  datetime.datetime of obseration

    output
    ------
    eci  x,y,z (meters)
    """
    if numpy is None:
        raise ImportError('aer2eci requires Numpy')
    x, y, z = aer2ecef(az, el, srange, lat0, lon0, h0, ell, deg)

    return ecef2eci(numpy.column_stack((x, y, z)), t)


def ecef2eci(ecef, t):
    """
    Point => Point

    input
    -----
    ecef:  Nx3  x,y,z  (meters)
    t:  datetime.datetime


    output
    ------
    eci  x,y,z (meters)
    """
    if Time is None or numpy is None:
        raise ImportError('ecef2eci requires Numpy and AstroPy')

    t = numpy.atleast_1d(t)
    if isinstance(t[0], string_types): #don't just ram in in case it's float
        t = str2dt(t)

    if isinstance(t[0], datetime):
        gst = Time(t).sidereal_time('apparent', 'greenwich').radian
    elif isinstance(t[0],float):
        gst = t
    else:
        raise TypeError('eci2ecef: time must be datetime or radian float')

    assert isinstance(gst[0], float)  # must be in radians!

    ecef = numpy.atleast_2d(ecef)
    N, trip = ecef.shape
    if ecef.ndim > 2 or trip != 3:
        raise TypeError('ecef triplets must be shape (N,3)')
    """ported from:
    https://github.com/dinkelk/astrodynamics/blob/master/rot3.m
    """
    eci = numpy.empty_like(ecef)
    for i in range(N):
        #eci[i, :] = _rottrip(gst[i]).T @ ecef[i, :] # this one is transposed
        eci[i, :] = _rottrip(gst[i]).T.dot(ecef[i, :]) # this one is transposed

    return eci
#%% to ENU
def aer2enu(az, el, srange, deg=True):
    """
    azimuth, elevation (degrees/radians)                             [0,360),[0,90]
    slant range [meters]                                             [0,Infinity)
    deg    degrees input/output  (False: radians in/out)

    output:
    -------
    e,n,u   East, North, Up [m]

    """
    if deg:
        el = radians(el)
        az = radians(az)

    r = srange * cos(el)

    return r * sin(az), r * cos(az), srange * sin(el)


def ecef2enu(x, y, z, lat0, lon0, h0, ell=None, deg=True):
    """

    input
    -----
    x,y,z  [meters] target ECEF location                             [0,Infinity)
    Observer: lat0, lon0, h0 (altitude, meters)
    ell    reference ellipsoid
    deg    degrees input/output  (False: radians in/out)

    output:
    -------
    e,n,u   East, North, Up [m]

    """
    x0, y0, z0 = geodetic2ecef(lat0, lon0, h0, ell, deg=deg)

    return _uvw2enu(x - x0, y - y0, z - z0, lat0, lon0, deg=deg)


def ecef2enuv(u, v, w, lat0, lon0, deg=True):
    """
    for VECTOR i.e. between two points

    input
    -----
    x,y,z  [meters] target ECEF location                             [0,Infinity)

    """
    if deg:
        lat0 = radians(lat0)
        lon0 = radians(lon0)

    t      =  cos(lon0) * u + sin(lon0) * v
    uEast  = -sin(lon0) * u + cos(lon0) * v
    wUp    =  cos(lat0) * t + sin(lat0) * w
    vNorth = -sin(lat0) * t + cos(lat0) * w

    return uEast, vNorth, wUp


def geodetic2enu(lat, lon, h, lat0, lon0, h0, ell=None, deg=True):
    """

    input
    -----
    target: lat,lon, h
    Observer: lat0, lon0, h0 (altitude, meters)
    ell    reference ellipsoid
    deg    degrees input/output  (False: radians in/out)


    output:
    -------
    e,n,u   East, North, Up [m]
    """
    x1, y1, z1 = geodetic2ecef(lat, lon, h, ell, deg=deg)
    x2, y2, z2 = geodetic2ecef(lat0, lon0, h0, ell, deg=deg)
    dx = x1 - x2
    dy = y1 - y2
    dz = z1 - z2

    return _uvw2enu(dx, dy, dz, lat0, lon0, deg=deg)
#%% to geodetic
def aer2geodetic(az, el, srange, lat0, lon0, h0, deg=True):
    """
    Input:
    -----
    az,el (degrees/radians)
    srange[meters]

    Observer: lat0,lon0 [degrees]
              altitude h0 [meters]

    deg :   degrees input/output  (False: radians in/out)

    output:
    WGS84 lat,lon [degrees]  h0altitude above spheroid  [meters]

    """
    x, y, z = aer2ecef(az, el, srange, lat0, lon0, h0, deg=deg)

    return ecef2geodetic(x, y, z, deg=deg)


def ecef2geodetic(x, y, z, ell=None, deg=True):
    """
    convert ECEF (meters) to geodetic coordinates

    input
    -----
    x,y,z  [meters] target ECEF location                             [0,Infinity)
    ell    reference ellipsoid
    deg    degrees input/output  (False: radians in/out)

    output
    ------
    lat,lon   (degrees/radians)
    alt  (meters)

    Algorithm is based on
    http://www.astro.uni.torun.pl/~kb/Papers/geod/Geod-BG.htm
    This algorithm provides a converging solution to the latitude equation
    in terms of the parametric or reduced latitude form (v)
    This algorithm provides a uniform solution over all latitudes as it does
    not involve division by cos(phi) or sin(phi)
    """

    if ell is None:
        ell = EarthEllipsoid()

    ea = ell.a
    eb = ell.b
    rad = hypot(x, y)
# Constant required for Latitude equation
    rho = arctan2(eb * z, ea * rad)
# Constant required for latitude equation
    c = (ea**2 - eb**2) / hypot(ea * rad, eb * z)
# Starter for the Newtons Iteration Method
    vnew = arctan2(ea * z, eb * rad)
# Initializing the parametric latitude
    v = 0
    for _ in range (5):
        v = deepcopy(vnew)
#%% Newtons Method for computing iterations
        vnew = v - ((2 * sin(v - rho) - c * sin(2 * v)) /
                    (2 * (cos(v - rho) - c * cos(2 * v))))

        if allclose(v,vnew):
            break
#%% Computing latitude from the root of the latitude equation
    lat = arctan2(ea * tan(vnew), eb)
    # by inspection
    lon = arctan2(y, x)

    alt = (((rad - ea * cos(vnew)) * cos(lat)) +
           ((z - eb * sin(vnew)) * sin(lat)))

    if deg:
        return degrees(lat), degrees(lon), alt
    else:
        return lat, lon, alt  # radians
"""
this is from PySatel and gives same result to EIGHT decimal places
def cbrt(x):
    if x >= 0:
        return pow(x, 1.0/3.0)
    else:
        return -pow(abs(x), 1.0/3.0)

def ecef2geodetic(x, y, z, ell=EarthEllipsoid(),deg=True):
    a = ell.a; b = ell.b
    esq = 6.69437999014*0.001
    e1sq = 6.73949674228*0.001
    r = hypot(x,y)
    Esq = a**2 - b**2
    F = 54 * b**2 * z**2
    G = r**2 + (1 - esq)* z**2 - esq*Esq
    C = (esq**2 *F* r**2)/(pow(G, 3))
    S = cbrt(1 + C + sqrt(C**2 + 2*C))
    P = F/(3* pow((S + 1/S + 1), 2)*G**2)
    Q = sqrt(1 + 2* esq**2 *P)
    r_0 =  -(P*esq*r)/(1 + Q) + sqrt(0.5* a**2 *(1 + 1.0/Q) - \
           P*(1 - esq)*z**2/(Q*(1 + Q)) - 0.5*P* r**2)
    U = sqrt(pow((r - esq*r_0), 2) + z**2)
    V = sqrt(pow((r - esq*r_0), 2) + (1 - esq)* z**2)
    Z_0 = b**2 *z/(a*V)
    alt = U*(1 - b**2/(a*V))
    lat = arctan((z + e1sq*Z_0)/r)
    lon = arctan2(y, x)

    if deg:
        return degrees(lat),degrees(lon),alt
    else:
        return lat, lon, alt #radians
"""

def eci2geodetic(eci, t):
    """
    convert ECI to geodetic coordinates

    inputs:

    eci/ecef: Nx3 vector of x,y,z triplets in the eci or ecef system [meters]
    t : length N vector of datetime OR greenwich sidereal time angle [radians].


    output
    ------
    lat,lon   (degrees/radians)
    alt  (meters)

    Note: Conversion is idealized: doesn't consider nutations, perterbations,
    etc. like the IAU-76/FK5 or IAU-2000/2006 model-based conversions
    from ECI to ECEF
    """

    """ a.k.a. eci2lla() """
    ecef = eci2ecef(eci, t)

    return ecef2geodetic(ecef[:, 0], ecef[:, 1], ecef[:, 2])


def enu2geodetic(e, n, u, lat0, lon0, h0,  ell=None, deg=True):
    """

    input
    -----
    e,n,u   East, North, Up [m]
    Observer: lat0, lon0, h0 (altitude, meters)
    ell    reference ellipsoid
    deg    degrees input/output  (False: radians in/out)


    output:
    -------
    target: lat,lon, h  (degrees/radians,degrees/radians, meters)

    """

    x, y, z = enu2ecef(e, n, u, lat0, lon0, h0, ell, deg=deg)

    return ecef2geodetic(x, y, z, ell, deg=deg)


def ned2geodetic(n, e, d, lat0, lon0, h0, ell=None, deg=True):
    """

    input
    -----
    n,e,d   North, east, down (meters)
    Observer: lat0, lon0, h0 (altitude, meters)
    ell    reference ellipsoid
    deg    degrees input/output  (False: radians in/out)


    output:
    -------
    target: lat,lon, h  (degrees/radians,degrees/radians, meters)

    """
    x, y, z = enu2ecef(e, n, -d, lat0, lon0, h0,  ell, deg=deg)

    return ecef2geodetic(x, y, z, ell, deg=deg)
# %% to NED

def aer2ned(az, elev, slantRange, deg=True):
    """
    input
    -----
    azimuth, elevation (degrees/radians)                             [0,360),[0,90]
    slant range [meters]                                             [0,Infinity)
    deg    degrees input/output  (False: radians in/out)

    output:
    -------
    n,e,d  North,east, down [m]
    """
    e, n, u = aer2enu(az, elev, slantRange, deg=deg)

    return n, e, -u


def ecef2ned(x, y, z, lat0, lon0, h0, ell=None, deg=True):
    """
    input
    -----
    x,y,z  [meters] target ECEF location                             [0,Infinity)
    Observer: lat0, lon0, h0 (altitude, meters)
    ell    reference ellipsoid
    deg    degrees input/output  (False: radians in/out)

    output:
    -------
    n,e,d  North,east, down [m]

    """
    e, n, u = ecef2enu(x, y, z, lat0, lon0, h0, ell, deg=deg)

    return n, e, -u


def ecef2nedv(u, v, w, lat0, lon0, deg=True):
    """
    for VECTOR between two points
    """
    e, n, u = ecef2enuv(u, v, w, lat0, lon0, deg=deg)

    return n, e, -u


def geodetic2ned(lat, lon, h, lat0, lon0, h0, ell=None, deg=True):
    """
    input
    -----
    target: lat,lon  (degrees/radians)
    h (altitude, meters)
    Observer: lat0, lon0 (degrees/radians)
    h0 (altitude, meters)
    ell    reference ellipsoid
    deg    degrees input/output  (False: radians in/out)


    output:
    -------
    n,e,d  North,east, down [m]
    """
    e, n, u = geodetic2enu(lat, lon, h, lat0, lon0, h0, ell, deg=deg)

    return n, e, -u

#%% shared functions

def get_radius_normal(lat_radians, ell):
    """ Compute normal radius of planetary body"""
    if ell is None:
        ell = EarthEllipsoid()


    a = ell.a
    b = ell.b

    return a**2 / sqrt(
        a**2 * (cos(lat_radians))**2 + b**2 *
        (sin(lat_radians))**2)
#%% internal use
def _rottrip(ang):
    ang = ang.squeeze()
    if ang.size > 1:
        raise ValueError('only one angle allowed at a time')
    """ported from:
    https://github.com/dinkelk/astrodynamics/blob/master/rot3.m
    """
    return numpy.array([[cos(ang),  sin(ang), 0],
                     [-sin(ang), cos(ang), 0],
                     [0,         0,        1]])


def _enu2uvw(east, north, up, lat0, lon0, deg=True):
    if deg:
        lat0 = radians(lat0)
        lon0 = radians(lon0)
    t = cos(lat0) * up - sin(lat0) * north
    w = sin(lat0) * up + cos(lat0) * north

    u = cos(lon0) * t - sin(lon0) * east
    v = sin(lon0) * t + cos(lon0) * east

    return u, v, w


def _uvw2enu(u, v, w, lat0, lon0, deg):
    if deg:
        lat0 = radians(lat0)
        lon0 = radians(lon0)
    t = cos(lon0) * u + sin(lon0) * v
    East = -sin(lon0) * u + cos(lon0) * v
    Up = cos(lat0) * t + sin(lat0) * w
    North = -sin(lat0) * t + cos(lat0) * w

    return East, North, Up

# %% azel radec
def azel2radec(az_deg, el_deg, lat_deg, lon_deg, t):
    """convert astronomical target horizontal azimuth, elevation to ecliptic right ascension, declination (degrees)"""

    if PY2 or Time is None: # non-AstroPy method, less accurate
        return vazel2radec(az_deg, el_deg, lat_deg, lon_deg, t)

    t = str2dt(t)

    obs = EarthLocation(lat=lat_deg * u.deg, lon=lon_deg * u.deg)

    direc = AltAz(location=obs, obstime=Time(t),
                  az=az_deg * u.deg, alt=el_deg * u.deg)

    sky = SkyCoord(direc.transform_to(ICRS()))

    return sky.ra.deg, sky.dec.deg


def radec2azel(ra_deg, dec_deg, lat_deg, lon_deg, t):
    """convert astronomical target ecliptic right ascension, declination to horizontal azimuth, eelvation (degrees)"""
    if numpy is None:
        raise ImportError('radec2azel requires Numpy')

    if Time is None:
        return vradec2azel(ra_deg, dec_deg, lat_deg, lon_deg, t)
#%% input trapping
    t = str2dt(t)
    lat_deg = numpy.atleast_1d(lat_deg)
    lon_deg = numpy.atleast_1d(lon_deg)
    ra_deg = numpy.atleast_1d(ra_deg)
    dec_deg = numpy.atleast_1d(dec_deg)

    assert lat_deg.size == 1 & lon_deg.size == 1, 'radec2azel is designed for one observer and one or more points (ra,dec).'
    assert ra_deg.shape == dec_deg.shape, 'ra and dec must be the same shape ndarray'

    obs = EarthLocation(lat=lat_deg * u.deg,
                        lon=lon_deg * u.deg)

    points = SkyCoord(Angle(ra_deg,  unit=u.deg),
                      Angle(dec_deg, unit=u.deg),
                      equinox='J2000.0')

    altaz = points.transform_to(AltAz(location=obs, obstime=Time(t)))

    return altaz.az.degree, altaz.alt.degree
# %%
def isclose(actual, desired, rtol=1e-7, atol=0):
    """
    rigourously evaluates closeness of values.
    https://www.python.org/dev/peps/pep-0485/#proposed-implementation
    """
    return abs(actual-desired) <= max(rtol * max(abs(actual), abs(desired)), atol)


def allclose(actual, desired, rtol=1e-7, atol=0):
    """1-D only version of numpy.testing.assert_allclose"""
    try:
        for a,d in zip(actual, desired):
            return isclose(a, d, rtol, atol)
    except TypeError:
        return isclose(actual, desired, rtol, atol)