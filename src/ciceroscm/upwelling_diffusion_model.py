"""
Energy budget upwelling diffusion model
"""
import logging

import numpy as np

from ._utils import check_numeric_pamset

SEC_DAY = 86400
DAY_YEAR = 365.0

LOGGER = logging.getLogger(__name__)


def check_pamset(pamset):
    """
    Check that parameterset has necessary values for run
    Otherwise set to default values
    """
    required = {
        "rlamdo": 16.0,
        "akapa": 0.634,
        "cpi": 0.4,
        "W": 4.0,
        "beto": 3.5,
        "threstemp": 7.0,
        "lambda": 0.540,
        "mixed": 60.0,
        "foan": 0.61,
        "foas": 0.81,
        "ebbeta": 0.0,
        "fnso": 0.7531,
        "lm": 40,
        "ldtime": 12,
    }
    pamset = check_numeric_pamset(required, pamset)
    pamset["rakapa"] = 1.0e-4 * pamset["akapa"]
    pamset["rlamda"] = 1.0 / pamset["lambda"]
    pamset["dt"] = 1 / pamset["ldtime"] * SEC_DAY * DAY_YEAR
    rho = 1.03
    htcpty = 0.955
    cnvrt = 0.485
    pamset["c1"] = rho * htcpty * cnvrt * 100.0 * SEC_DAY
    pamset["fnx"] = (
        pamset["rlamda"] + pamset["foan"] * pamset["rlamdo"] + pamset["ebbeta"]
    )
    pamset["fsx"] = (
        pamset["rlamda"] + pamset["foas"] * pamset["rlamdo"] + pamset["ebbeta"]
    )
    return pamset


def _coefic(s, t, p):
    """
    Calculate denisty coefficients
    """
    coefic = (
        19652.21
        + 148.4206 * t
        - 2.327105 * t ** 2
        + 1.360477e-2 * t ** 3
        - 5.155288e-5 * t ** 4
        + 3.239908 * p
        + 1.43713e-3 * t * p
        + 1.16092e-4 * t ** 2 * p
        - 5.77905e-7 * t ** 3 * p
        + 8.50935e-5 * p ** 2
        - 6.12293e-6 * t * p ** 2
        + 5.2787e-8 * t ** 2 * p ** 2
        + 54.6746 * s
        - 0.603459 * t * s
        + 1.09987e-2 * t ** 2 * s
        - 6.1670e-5 * t ** 3 * s
        + 7.944e-2 * s ** 1.5
        + 1.6483e-2 * t * s ** 1.5
        - 5.3009e-4 * t ** 2 * s ** 1.5
        + 2.2838e-3 * p * s
        - 1.0981e-5 * t * p * s
        - 1.6078e-6 * t ** 2 * p * s
        + 1.91075e-4 * p * s ** 1.5
        - 9.9348e-7 * p ** 2 * s
        + 2.0816e-8 * t * p ** 2 * s
        + 9.1697e-10 * t ** 2 * p ** 2 * s
    )
    return coefic


def _denso(s, t):
    """
    Calculate density at p0=0
    """
    denso = (
        999.842594
        + 6.793952e-2 * t
        - 9.095290e-3 * t ** 2
        + 1.001685e-4 * t ** 3
        - 1.120083e-6 * t ** 4
        + 6.536332e-9 * t ** 5
        + 8.24493e-1 * s
        - 4.0899e-3 * t * s
        + 7.6438e-5 * t ** 2 * s
        - 8.2467e-7 * t ** 3 * s
        + 5.3875e-9 * t ** 4 * s
        - 5.72466e-3 * s ** 1.5
        + 1.0227e-4 * t * s ** 1.5
        - 1.6546e-6 * t ** 2 * s ** 1.5
        + 4.8314e-4 * s ** 2
    )
    return denso


def _density(p0, t0):
    """
    Calculate water denisity from equation of state
    """
    s = 35.0
    return _denso(s, t0) / (1.0 - p0 / _coefic(s, t0, p0))


class UpwellingDiffusionModel:  # pylint: disable=too-many-instance-attributes
    """
    Class to handle energy budget upwelling and downwelling
    """

    def __init__(self, params):
        """
        Intialise
        """
        self.pamset = check_pamset(params)

        # Setting up dz height difference between ocean layers
        self.dz = np.ones(self.pamset["lm"]) * 100.0
        self.dz[0] = params["mixed"]
        self.varrying = {}
        self.setup_ebud()

        # Intialising temperature values
        self.tn = np.zeros(self.pamset["lm"])
        self.ts = np.zeros(self.pamset["lm"])
        # Dict of values to keep from one year to the next
        self.prev_values = {
            "zso": 0.0,
            "zgo": 0.0,
            "zao": 0.0,
            "fn": 0.0,
            "fs": 0.0,
            "dtemp": 0.0,
        }

        self.dtempprev = 0.0
        self.setup_sealevel_rise()

    def _band(self, a_array, b_array, c_array, d_array):
        """
        Calculate band
        """
        alfa = np.zeros(self.pamset["lm"] - 1)
        ans = np.zeros(self.pamset["lm"])
        bbeta = np.zeros(self.pamset["lm"] - 1)

        alfa[0] = -b_array[0] / a_array[0]
        bbeta[0] = d_array[0] / a_array[0]

        for i in range(1, self.pamset["lm"] - 1):
            tem = a_array[i] * alfa[i - 1] + b_array[i]
            alfa[i] = -c_array[i] / tem
            bbeta[i] = (d_array[i] - a_array[i] * bbeta[i - 1]) / tem
        tem = (
            a_array[self.pamset["lm"] - 1] * alfa[self.pamset["lm"] - 2]
            + b_array[self.pamset["lm"] - 1]
        )
        ans[self.pamset["lm"] - 1] = (
            d_array[self.pamset["lm"] - 1]
            - a_array[self.pamset["lm"] - 1] * bbeta[self.pamset["lm"] - 2]
        ) / tem

        for i in range(1, self.pamset["lm"]):
            j = self.pamset["lm"] - 1 - i
            ans[j] = alfa[j] * ans[j + 1] + bbeta[j]

        return ans

    def get_gam_and_fro_factor_ns(self, northern_hemisphere):
        """
        Get correct cam and fro variables depending on
        whether Northern or Southern hemispher is
        considered
        """
        blm = self.pamset["ebbeta"] / self.pamset["rlamdo"]
        if northern_hemisphere:
            gam1 = self.gamn
            gam2 = self.gams
            fro1 = self.pamset["foan"]
        else:
            gam1 = self.gams
            gam2 = self.gamn
            fro1 = self.pamset["foas"]
        factor = (
            self.pamset["rlamdo"]
            * (1.0 - fro1 * gam2 / (gam2 * gam1 - blm * blm))
            * self.pamset["dt"]
            / (self.pamset["c1"] * self.dz[0])
        )
        return factor

    def coeff(self, wcfac, gam_fro_fac):
        """
        Calculate a, b c coefficient arrays for hemisphere
        """
        lm = self.pamset["lm"]
        a = np.zeros(lm)
        b = np.zeros(lm)
        c = np.zeros(lm)
        rakapafac = 2 * self.pamset["rakapa"] * self.pamset["dt"]

        b[0] = -rakapafac / (
            self.dz[0] * (0.0 * self.dz[0] + self.dz[1])
        )  # Can the 0.*dz(0) term be dropped here?
        a[0] = 1.0 - b[0] + gam_fro_fac - wcfac / self.dz[0]
        a[1] = -rakapafac / (self.dz[1] ** 2) + wcfac / self.dz[1]
        a[2:] = -rakapafac / (self.dz[2:] * (self.dz[1 : lm - 1] + self.dz[2:]))
        c[1 : lm - 1] = (
            -rakapafac / (self.dz[1 : lm - 1] * (self.dz[1 : lm - 1] + self.dz[2:]))
            - wcfac / self.dz[1 : lm - 1]
        )
        b[1 : lm - 1] = 1.0 - a[1 : lm - 1] - c[1 : lm - 1]
        b[lm - 1] = (
            1.0 - a[lm - 1] + wcfac / self.dz[lm - 1]
        )  # Her var det brukt i selvom vi var utenfor loekka, litt uklart hva som er ment...
        return a, b, c

    def setup_ebud2(self, temp_1n, temp_1s):
        """
        Set up coefficients and more for the two hemispheres
        to be redone every timestep
        """
        # Northern hemisphere:
        if self.pamset["threstemp"] == 0:  # pylint: disable=compare-to-zero
            wcfac = self.pamset["W"] / (SEC_DAY * DAY_YEAR) * self.pamset["dt"]
        else:
            wcfac = (
                self.pamset["W"]
                / (SEC_DAY * DAY_YEAR)
                * (1 - 0.3 * temp_1n / self.pamset["threstemp"])
                * self.pamset["dt"]
            )
        self.varrying["dtrm1n"] = (
            1.0
            - self.pamset["cpi"] * wcfac / self.dz[0]
            - self.pamset["beto"] * self.pamset["dt"] / (self.pamset["c1"] * self.dz[0])
        )
        self.varrying["dtmnl2"] = (
            wcfac * self.pamset["cpi"] / self.dz[self.pamset["lm"] - 1]
        )
        (
            self.varrying["acoeffn"],
            self.varrying["bcoeffn"],
            self.varrying["ccoeffn"],
        ) = self.coeff(wcfac, self.get_gam_and_fro_factor_ns(True))

        # Southern hemisphere:
        if self.pamset["threstemp"] == 0:  # pylint: disable=compare-to-zero
            wcfac = self.pamset["W"] / (SEC_DAY * DAY_YEAR) * self.pamset["dt"]
        else:
            wcfac = (
                self.pamset["W"]
                / (SEC_DAY * DAY_YEAR)
                * (1 - 0.3 * temp_1s / self.pamset["threstemp"])
                * self.pamset["dt"]
            )
        self.varrying["dtrm1s"] = (
            1.0
            - self.pamset["cpi"] * wcfac / self.dz[0]
            - self.pamset["fnso"]
            * self.pamset["beto"]
            * self.pamset["dt"]
            / (self.pamset["c1"] * self.dz[0])
        )
        self.varrying["dtmsl2"] = (
            wcfac * self.pamset["cpi"] / self.dz[self.pamset["lm"] - 1]
        )
        (
            self.varrying["acoeffs"],
            self.varrying["bcoeffs"],
            self.varrying["ccoeffs"],
        ) = self.coeff(wcfac, self.get_gam_and_fro_factor_ns(False))

    def setup_ebud(self):
        """
        Set up energy budget before run
        """
        fnsa = 1.0  # Can it be something else?
        c1fac = self.pamset["dt"] / (self.pamset["c1"] * self.dz[0])

        blm = self.pamset["ebbeta"] / self.pamset["rlamdo"]
        self.gamn = (
            self.pamset["foan"] + self.pamset["rlamda"] / self.pamset["rlamdo"] + blm
        )
        self.gams = (
            self.pamset["foas"]
            + self.pamset["rlamda"] / self.pamset["rlamdo"]
            + fnsa * blm
        )

        # Northern hemisphere
        self.varrying["dtrm2n"] = (
            self.pamset["beto"]
            + self.pamset["foas"]
            * self.pamset["ebbeta"]
            / (self.gams * self.gamn - fnsa * blm ** 2)
        ) * c1fac
        self.varrying["dtrm3n"] = (
            self.gams / (self.gams * self.gamn - fnsa * blm ** 2) * c1fac
        )
        self.varrying["dtrm4n"] = (
            blm / (self.gams * self.gamn - fnsa * blm ** 2) * c1fac
        )

        # Southern hemisphere
        self.varrying["dtrm2s"] = (
            self.pamset["fnso"] * self.pamset["beto"]
            + self.pamset["foan"]
            * fnsa
            * self.pamset["ebbeta"]
            / (self.gams * self.gamn - fnsa * blm ** 2)
        ) * c1fac
        self.varrying["dtrm3s"] = (
            self.gamn / (self.gams * self.gamn - fnsa * blm ** 2) * c1fac
        )
        self.varrying["dtrm4s"] = (
            fnsa * blm / (self.gams * self.gamn - fnsa * blm ** 2) * c1fac
        )

        self.varrying["dtmnl3"] = (
            self.pamset["dt"]
            * self.pamset["beto"]
            / (self.pamset["c1"] * self.dz[self.pamset["lm"] - 1])
        )
        self.varrying["dtmnl1"] = 1.0 - self.varrying["dtmnl3"]
        self.varrying["dtmsl3"] = self.pamset["fnso"] * self.varrying["dtmnl3"]
        self.varrying["dtmsl1"] = 1.0 - self.varrying["dtmsl3"]
        self.setup_ebud2(0, 0)

    def setup_sealevel_rise(self):
        """
        Set up variables to be used in sea level rise calculations
        """
        self.press = np.zeros(self.pamset["lm"])
        self.tempunp = np.zeros(self.pamset["lm"])
        self.press[0] = 35.0 * 1.0e4 * 1.0e-5
        self.tempunp[0] = 19.5
        self.dens0 = np.zeros(self.pamset["lm"])
        self.dens0[0] = _density(self.press[0], self.tempunp[0])
        self.press[1:] = np.array(
            [12.0 + 10.0 * (i - 1) for i in range(1, self.pamset["lm"])]
        )
        self.tempunp[1:] = np.array(
            [
                125.98 * (120.0 + 100.0 * (i - 1)) ** (-0.45952)
                for i in range(1, self.pamset["lm"])
            ]
        )
        density = np.vectorize(_density)
        self.dens0[1:] = density(self.press[1:], self.tempunp[1:])
        # self.dens0[1:] = np.array([])
        # for i in range(1, self.pamset["lm"]):
        #    z = 120.0 + 100.0 * (i - 1)  # Skulle 120. = mixed?
        #    self.press[i] = z * 1.0e4  # Units=Pa
        #    self.press[i] = self.press[i] * 1.0e-5  # Units=bar
        #    self.tempunp[i] = 125.98 * z ** (-0.45952)
        #    self.dens0[i] = _density(self.press[i], self.tempunp[i])

    def compute_sea_level_rise(self, templ, dtemp):
        """
        Compute sea level rise associated with temperature change
        """
        betag = 3.0e-4  # Make changeable parameter?
        betaa = -2.0e-4  # Make changeable parameter?
        betas = 0.25  # Make changeable parameter?
        ebtau = 20  # Make changeable parameter?
        z0_param = 0.5  # Make changeable parameter?
        deltsl = np.zeros(2)

        # Sea level rise from temperature change
        for i in range(self.pamset["lm"]):
            dens1 = _density(self.press[i], (templ[i] + self.tempunp[i]))
            deldens = dens1 - self.dens0[i]
            deltsl[0] = deltsl[0] - deldens * self.dz[i] / dens1

        # Sea level rise from melting Ice sheets
        # Maybe outdated
        # Also why not use hemispheric temperature change?
        # Greenland
        self.prev_values["zgo"] = (
            self.prev_values["zgo"]
            + 1.5 * betag * (dtemp + self.prev_values["dtemp"]) / 2.0
        )
        # Antarctica
        self.prev_values["zao"] = (
            self.prev_values["zao"] + betaa * (dtemp + self.prev_values["dtemp"]) / 2.0
        )
        # Small glaciers:
        aa = self.prev_values["zso"] + z0_param * betas * dtemp / ebtau
        bb = 1.0 + (1.0 + betas * dtemp) / ebtau
        self.prev_values["zso"] = aa / bb

        deltsl[1] = (
            self.prev_values["zgo"] + self.prev_values["zao"] + self.prev_values["zso"]
        )
        return deltsl

    def energy_budget(
        self, forc_nh, forc_sh, fn_volc, fs_volc
    ):  # pylint: disable=too-many-locals
        """
        Do energy budget calculation for single year
        """
        temp1n = 0.0
        temp1s = 0.0

        tempn = 0.0
        temps = 0.0
        tempn_air = 0.0
        temps_air = 0.0
        tempn_sea = 0.0
        temps_sea = 0.0
        lm = self.pamset["lm"]
        templ = np.zeros(lm)

        dtyear = 1.0 / self.pamset["ldtime"]
        dn = np.zeros(lm)
        ds = np.zeros(lm)

        for im in range(self.pamset["ldtime"]):

            if self.pamset["threstemp"] != 0:  # pylint: disable=compare-to-zero
                self.setup_ebud2(temp1n, temp1s)

            dqn = (
                (im + 1) * forc_nh * dtyear
                + (1 - (im + 1) * dtyear) * self.prev_values["fn"]
                + fn_volc[im]
            )
            dqs = (
                (im + 1) * forc_sh * dtyear
                + (1 - (im + 1) * dtyear) * self.prev_values["fs"]
                + fs_volc[im]
            )
            dn[0] = (
                self.varrying["dtrm1n"] * self.tn[0]
                + self.varrying["dtrm2n"] * self.ts[0]
                + self.varrying["dtrm3n"] * dqn
                + self.varrying["dtrm4n"] * dqs
            )
            ds[0] = (
                self.varrying["dtrm1s"] * self.ts[0]
                + self.varrying["dtrm2s"] * self.tn[0]
                + self.varrying["dtrm3s"] * dqs
                + self.varrying["dtrm4s"] * dqn
            )
            dn[1 : lm - 1] = self.tn[1 : lm - 1] + self.pamset["beto"] * self.pamset[
                "dt"
            ] / (self.pamset["c1"] * self.dz[1 : lm - 1]) * (
                self.ts[1 : lm - 1] - self.tn[1 : lm - 1]
            )
            ds[1 : lm - 1] = self.ts[1 : lm - 1] + self.pamset["fnso"] * self.pamset[
                "beto"
            ] * self.pamset["dt"] / (self.pamset["c1"] * self.dz[1 : lm - 1]) * (
                self.tn[1 : lm - 1] - self.ts[1 : lm - 1]
            )

            dn[lm - 1] = (
                self.varrying["dtmnl1"] * self.tn[lm - 1]
                + self.varrying["dtmnl2"] * self.tn[0]
                + self.varrying["dtmnl3"] * self.ts[lm - 1]
            )
            ds[lm - 1] = (
                self.varrying["dtmsl1"] * self.ts[lm - 1]
                + self.varrying["dtmsl2"] * self.ts[0]
                + self.varrying["dtmsl3"] * self.tn[lm - 1]
            )

            #
            # Where are these being initialised? Ok, I think
            self.tn = self._band(
                self.varrying["acoeffn"],
                self.varrying["bcoeffn"],
                self.varrying["ccoeffn"],
                dn,
            )
            self.ts = self._band(
                self.varrying["acoeffs"],
                self.varrying["bcoeffs"],
                self.varrying["ccoeffs"],
                ds,
            )
            # print("self.aceoffn: %s self.varrying["bcoeffn"]: %s self.ccoeffn %s"%(self.varrying["acoeffn"], self.varrying["bcoeffn"], self.varrying["ccoeffn"]))
            # print("self.aceoffs: %s self.bcoeffs: %s self.ccoeffs %s"%(self.varrying["acoeffs"], self.bcoeffs, self.ccoeffs))
            temp1n = self.tn[0]
            temp1s = self.ts[0]
            # print("temp1n: %.5e temp1s %.5e"%(temp1n, temp1s))
            templ = (
                templ + 0.5 * (self.tn + self.ts) / 12.0
            )  # skulle 12 her vrt ldtime?

            tempan = (
                dqn
                + self.pamset["foan"] * self.pamset["rlamdo"] * temp1n
                + self.pamset["ebbeta"]
                * (dqs + self.pamset["foas"] * self.pamset["rlamdo"] * temp1s)
                / self.pamset["fsx"]
            )
            tempan = tempan / (
                self.pamset["fnx"] - self.pamset["ebbeta"] ** 2 / self.pamset["fsx"]
            )
            tempas = (
                dqs
                + self.pamset["foas"] * self.pamset["rlamdo"] * temp1s
                + self.pamset["ebbeta"]
                * (dqn + self.pamset["foan"] * self.pamset["rlamdo"] * temp1n)
                / self.pamset["fnx"]
            )
            tempas = tempas / (
                self.pamset["fsx"] - self.pamset["ebbeta"] ** 2 / self.pamset["fnx"]
            )
            tmpn = self.pamset["foan"] * temp1n + (1.0 - self.pamset["foan"]) * tempan
            tmps = self.pamset["foas"] * temp1s + (1.0 - self.pamset["foas"]) * tempas

            # x1=1638.+float(years_since_start)+float(im-1)/12.

            tempn = tempn + tmpn / 12.0
            temps = temps + tmps / 12.0

            tempn_air = tempn_air + tempan / 12.0
            temps_air = temps_air + tempas / 12.0

            tempn_sea = tempn_sea + temp1n / 12.0
            temps_sea = temps_sea + temp1s / 12

        dtemp = (tempn + temps) / 2.0  # Global temp chg)

        deltsl = self.compute_sea_level_rise(templ, dtemp)
        # Updating previous values for next year
        self.prev_values["fn"] = forc_nh
        self.prev_values["fs"] = forc_sh
        self.prev_values["dtemp"] = dtemp

        # Getting Ocean temperature:
        ocean_res = self.compute_ocean_temperature()
        ribn = (
            forc_nh
            + np.sum(fn_volc) / self.pamset["ldtime"]
            - self.pamset["rlamda"] * tempn
        )
        ribs = (
            forc_sh
            + np.sum(fs_volc) / self.pamset["ldtime"]
            - self.pamset["rlamda"] * temps
        )
        # Returning results_dict
        return {
            "dtemp": dtemp,
            "dtempnh": tempn,
            "dtempsh": temps,
            "dtemp_air": (tempn_air + temps_air) / 2.0,
            "dtempnh_air": tempn_air,
            "dtempsh_air": temps_air,
            "dtemp_sea": (tempn_sea + temps_sea) / 2.0,
            "dtempnh_sea": tempn_sea,
            "dtempsh_sea": temps_sea,
            "RIBN": ribn,
            "RIBS": ribs,
            "RIB": (ribn + ribs) / 2.0,
            "deltsl": deltsl,
            "OHC700": ocean_res["OHC700"],
            "OHCTOT": ocean_res["OHCTOT"],
        }

    def compute_ocean_temperature(self):
        """
        Compute the ocean temperature total and at 700 m depth
        """
        area_hemisphere = 2.55e14

        rho = 1030.0
        constant = 3.997e-19
        havtemp = (
            rho
            * constant
            * area_hemisphere
            * self.dz
            * (self.tn * self.pamset["foan"] + self.ts * self.pamset["foas"])
        )

        # Finding the max layer down to 700m
        max_layer = int(7 - self.dz[0] // 100.0)
        frac = (1 + self.dz[0] // 100.0) - self.dz[0] / 100.0

        return {
            "OHC700": np.sum(havtemp[:max_layer]) + frac * havtemp[max_layer],
            "OHCTOT": np.sum(havtemp[:]),
        }
