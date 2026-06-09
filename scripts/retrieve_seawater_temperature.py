# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT
"""
Retrieve seawater temperature data from Copernicus Marine Service.

This script downloads historical seawater temperature data for use in sea water
heat pump calculations. It retrieves potential temperature (thetao) data from
the global ocean physics reanalysis dataset at daily resolution.

The data covers European coastal areas at a spatial resolution of 0.083° and
includes near-surface depths (5-15m) suitable for heat pump applications.

Relevant Settings
-----------------

```yaml
# No specific configuration required
# Uses year wildcard from Snakemake rule
```

Inputs
------
- None (downloads from Copernicus Marine Service)

Outputs
-------
- `data/seawater_temperature_{year}.nc`: NetCDF file containing seawater temperature data

Notes
-----
Requires Copernicus Marine Service credentials configured via copernicusmarine package.
See https://marine.copernicus.eu/ for account setup and API access.
"""

import logging
import os

import copernicusmarine
import requests

from scripts._helpers import (
    configure_logging,
    set_scenario_config,
    update_config_from_wildcards,
)

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    if "snakemake" not in globals():
        from _helpers import mock_snakemake

        snakemake = mock_snakemake(
            "retrieve_seawater_temperature",
            clusters="39",
            opts="",
            ll="vopt",
            sector_opts="",
            planning_horizons=2050,
        )

    # Configure logging and scenario
    configure_logging(snakemake)
    set_scenario_config(snakemake)
    update_config_from_wildcards(snakemake.config, snakemake.wildcards)

    if snakemake.params.default_cutout == "be-03-2013-era5":
        logger.info("Retrieving test-cutout seawater temperature data.")

        url = snakemake.params.test_data_url

        response = requests.get(url, stream=True)
        response.raise_for_status()

        with open(snakemake.output.seawater_temperature, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        logger.info(
            f"Successfully downloaded test-cutout seawater temperature data to {snakemake.output.seawater_temperature}"
        )
    else:
        # Determine data year: use override year from config if set,
        # otherwise use the wildcard year directly.
        override_year = snakemake.config.get("sector", {}).get(
            "seawater_temperature_year"
        )
        target_year = int(snakemake.wildcards.year)
        data_year = override_year if override_year is not None else target_year

        logger.info(
            f"Downloading seawater temperature data for year {data_year}"
        )

        _ = copernicusmarine.subset(
            dataset_id="cmems_mod_glo_phy_my_0.083deg_P1D-m",  # Global ocean physics reanalysis
            start_datetime=f"{data_year}-01-01",
            end_datetime=f"{data_year}-12-31",
            minimum_longitude=-12,  # Western European boundary
            maximum_longitude=42,  # Eastern European boundary
            minimum_latitude=33,  # Southern European boundary
            maximum_latitude=72,  # Northern European boundary
            variables=["thetao"],  # Potential temperature [°C]
            minimum_depth=5,  # Near-surface depth for heat pumps [m]
            maximum_depth=15,  # Near-surface depth for heat pumps [m]
            output_filename=snakemake.output.seawater_temperature,
        )

        # Verify successful download
        if not os.path.exists(snakemake.output.seawater_temperature):
            raise FileNotFoundError(
                f"Failed to retrieve seawater temperature data and save to {snakemake.output.seawater_temperature}. "
                f"One reason might be missing Copernicus Marine login info. "
                f"See the copernicusmarine package documentation for details."
            )

        # Drop Feb 29 from downloaded data to avoid leap-day issues downstream
        import os as _os
        import xarray as xr

        with xr.open_dataset(snakemake.output.seawater_temperature) as ds:
            has_leap_day = ((ds.indexes["time"].month == 2) & (ds.indexes["time"].day == 29)).any()
            if has_leap_day:
                logger.info("Dropping Feb 29 from seawater temperature data")
                ds = ds.sel(time=~((ds.time.dt.month == 2) & (ds.time.dt.day == 29)))
                tmp = snakemake.output.seawater_temperature + ".tmp"
                ds.to_netcdf(tmp)
                _os.replace(tmp, snakemake.output.seawater_temperature)

        logger.info(
            f"Successfully downloaded seawater temperature data to {snakemake.output.seawater_temperature}"
        )
