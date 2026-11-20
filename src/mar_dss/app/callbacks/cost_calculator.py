import numpy as np
import pandas as pd

import mar_dss.app.utils.data_storage as dash_storage

# default_engineering_elements = {
#    "Flow Capture Structure": True,
#    "Rough Grading/Grubbing in Field":True,


#    "Sediment Removal Pond":True, #
#    "Conveyance to Sediment Removal Pond":"Trapezoidal Channel", # "Gravity Conveyance Pipeline" or "Pumped Conveyance"
#    "Sediment Removal Target":"Medium Silt", # "Medium Silt" or ""Fine Silt"
#    "Contaminant Filters":False, #

#    "Storage Pond":True, #
#    "Pipeline to Storage Pond":True, #
#    "Pump to Storage Pond":True, #
#    "Controls for Storage Pond":True, #
#    "Electrical System for Storage Pond":True, #

#    "Pipeline to Infiltration Site":True, #
#    "Pump to Infiltration Site":True, #
#    "Controls for Infiltration Site":True, #
#    "Electrical System for Infiltration Site":True, #

#    "Dry Wells Infiltration":"None", # "Dry Wells Infiltration" or "None"
#    "Injection Wells Infiltration":"None", # "Injection Wells Infiltration" or "None"
#    "Infiltration Basin":"None", # "Infiltration Basin" or "None"

# }


class CostCalculator:
    def __init__(
        self,
        water_source: str | None = None,
        storm_design_depth: float | None = None,
        drainage_basin_area_acres: float | None = None,
        total_storm_volume_af: float | None = None,  # likely not
        basin_soil_type_infiltration_rate_in_per_hr: float | None = None,
        percentage_storm_volume_to_capture: float | None = None,
        total_runoff_volume_ft3: float | None = None,
        distance_collection_to_sediment_pond_ft: float | None = None,
        distance_sediment_to_storage_pond_ft: float | None = None,
        sediment_pond_area_available_acres: float | None = None,
        fine_sediment_removal_goal: str | None = None,
        dry_well_infiltration_rate_in_per_hr: float | None = None,
        dry_well_transfer_rate_gpm: float | None = None,
        number_of_injection_wells: int | None = None,
        injection_well_transfer_rate_gpm: float | None = None,
        dry_well_diameter_ft: float | None = None,
        collection_to_sediment_removal__conveyance_method: str | None = None,
        recharge_method: str | None = None,
        number_of_dry_wells: int | None = None,
        dry_well_Q_ft3_per_day: float | None = None,
    ):
        """Initialize MAR Cost Calculator with project parameters."""
        if water_source is not None:
            water_source_lower = water_source.lower()
            if water_source_lower == "stormwater":
                self.storm_design_depth = storm_design_depth
                self.drainage_basin_area_acres = drainage_basin_area_acres
                self.total_storm_volume_af = total_runoff_volume_ft3 / 43560.0
                # todo: not used, remove if not needed
                self.basin_soil_type_infiltration_rate_in_per_hr = basin_soil_type_infiltration_rate_in_per_hr
                self.percentage_storm_volume_to_capture = percentage_storm_volume_to_capture
                self.total_runoff_volume_ft3 = total_runoff_volume_ft3
            elif water_source_lower == "treated_wastewater" or water_source_lower == "brackish_water":
                pass
            else:
                raise ValueError(
                    f"Invalid water source: {water_source}. "
                    f"Valid options: 'stormwater', "
                    f"'treated_wastewater', 'brackish_water'",
                )

        self.water_source = water_source
        if fine_sediment_removal_goal in ["Fine Silt", "Medium Silt"]:
            self.sediment_type = fine_sediment_removal_goal
        else:
            raise ValueError(f"Invalid fine_sediment_removal_goal: {fine_sediment_removal_goal}.")

        self.distance_collection_to_sediment_pond_ft = distance_collection_to_sediment_pond_ft
        self.distance_sediment_to_storage_pond_ft = distance_sediment_to_storage_pond_ft
        if collection_to_sediment_removal__conveyance_method in [
            "gravity_ditch",
            "gravity_pipeline",
            "pumped_pipeline",
            "pumped_ditch",
            # Legacy values (migrated at call sites; still accepted)
            "trapezoidal",
            "pipeline",
            "pumped",
        ]:
            legacy = {
                "trapezoidal": "gravity_ditch",
                "pipeline": "gravity_pipeline",
                "pumped": "pumped_pipeline",
            }
            method = legacy.get(
                collection_to_sediment_removal__conveyance_method,
                collection_to_sediment_removal__conveyance_method,
            )
            self.collection_to_sediment_removal__conveyance_method = method
        else:
            raise ValueError(
                f"Invalid "
                f"collection_to_sediment_removal__conveyance_method: "
                f"{collection_to_sediment_removal__conveyance_method}. "
                f"Valid options: 'gravity_ditch', 'gravity_pipeline', "
                f"'pumped_pipeline', 'pumped_ditch'",
            )

        self.sediment_pond_area_available_acres = sediment_pond_area_available_acres

        feasible_options = ["Fine Silt", "Medium Silt", "Coarse Silt", "Sand"]
        if fine_sediment_removal_goal is not None:
            if fine_sediment_removal_goal not in feasible_options:
                raise ValueError(
                    f"Invalid fine_sediment_removal_goal: "
                    f"{fine_sediment_removal_goal}. "
                    f"Feasible options are: "
                    f"{', '.join(feasible_options)}",
                )
        self.fine_sediment_removal_goal = fine_sediment_removal_goal

        self.dry_well_diameter_ft = dry_well_diameter_ft
        self.dry_well_infiltration_rate_in_per_hr = dry_well_infiltration_rate_in_per_hr
        self.dry_well_transfer_rate_gpm = dry_well_transfer_rate_gpm
        self.injection_well_transfer_rate_gpm = injection_well_transfer_rate_gpm
        self.number_of_injection_wells = number_of_injection_wells
        self.number_of_dry_wells = number_of_dry_wells
        self.dry_well_Q_ft3_per_day = dry_well_Q_ft3_per_day

        if recharge_method in ["dry_well", "injection_well", "infiltration_basin"]:
            self.recharge_method = recharge_method
        else:
            raise ValueError(
                f"Invalid recharge_method: {recharge_method}. "
                f"Valid options: 'dry_well', 'injection_well', "
                f"'infiltration_basin'",
            )

    def calculate_cost(self):
        # self.read_engineering_elements()
        self.hydro_calculations()
        self.conveyance_calculations()
        self.sediment_removal_pond()
        self.pump_conveyance_to_sediment_removal_pond()
        self.buried_pipeline_cost()
        self.storage_pond()
        self.dry_wells_infiltration()
        self.injection_wells_infiltration()
        self.infiltration_basin()
        self.capital_costs()
        self.maintenance_costs()
        self.net_present_value()

    # def read_engineering_elements(self):
    #     # todo: read from data storage
    #     self.engineering_elements = default_engineering_elements

    def hydro_calculations(self):
        class Hydro:
            pass

        hydro = Hydro()
        hydro.basin_area_acres = self.drainage_basin_area_acres
        hydro.basin_area_ft2 = self.drainage_basin_area_acres * 43560

        peak_flow_rate_ft3_per_hour = self.total_runoff_volume_ft3 / 12.0
        self.peak_flow_rate_gpm = peak_flow_rate_ft3_per_hour * 0.124675
        hydro.total_storm_volume_gals = self.total_storm_volume_af * 325851.43

        # assuming triangular unit hydrograph, height is h and base 24 hours
        # the peak flow if total runoff volume is V

        self.hydro = hydro

    def conveyance_calculations(self):
        class Conveyance:
            pass

        conveyance = Conveyance()

        conveyance.culvert_size_table = [
            {"size_inches": 6, "area_ft2": 0.343, "flow_capacity_gpm": 153.9, "velocity_fps": 1.75},
            {"size_inches": 12, "area_ft2": 1.821, "flow_capacity_gpm": 817.3, "velocity_fps": 2.32},
            {"size_inches": 18, "area_ft2": 5.087, "flow_capacity_gpm": 2283.2, "velocity_fps": 2.88},
            {"size_inches": 24, "area_ft2": 10.959, "flow_capacity_gpm": 4918.7, "velocity_fps": 3.49},
            {"size_inches": 36, "area_ft2": 32.358, "flow_capacity_gpm": 14523.2, "velocity_fps": 4.58},
            {"size_inches": 48, "area_ft2": 69.708, "flow_capacity_gpm": 31287.0, "velocity_fps": 5.55},
            {"size_inches": 60, "area_ft2": 126.385, "flow_capacity_gpm": 56725.4, "velocity_fps": 6.44},
            {"size_inches": 72, "area_ft2": 205.45, "flow_capacity_gpm": 92212.1, "velocity_fps": 7.27},
        ]

        conveyance.trapezoidal_channel_table = [
            {"bottom_width_ft": None, "depth_ft": 0.5, "flowrate_cfs": 1.03, "flowrate_gpm": 462, "cost_per_foot": 5},
            {"bottom_width_ft": None, "depth_ft": 1, "flowrate_cfs": 6.56, "flowrate_gpm": 2944, "cost_per_foot": 32},
            {"bottom_width_ft": 3, "depth_ft": 1.5, "flowrate_cfs": 19.33, "flowrate_gpm": 8675, "cost_per_foot": 93},
            {"bottom_width_ft": 4, "depth_ft": 2, "flowrate_cfs": 41.64, "flowrate_gpm": 18688, "cost_per_foot": 200},
            {"bottom_width_ft": 6, "depth_ft": 3, "flowrate_cfs": 122.76, "flowrate_gpm": 55095, "cost_per_foot": 590},
            {
                "bottom_width_ft": 8,
                "depth_ft": 4,
                "flowrate_cfs": 264.38,
                "flowrate_gpm": 118654,
                "cost_per_foot": 1270,
            },
            {
                "bottom_width_ft": 9,
                "depth_ft": 4.5,
                "flowrate_cfs": 361.94,
                "flowrate_gpm": 162439,
                "cost_per_foot": 1738,
            },
            {
                "bottom_width_ft": 10,
                "depth_ft": 5,
                "flowrate_cfs": 479.35,
                "flowrate_gpm": 215132,
                "cost_per_foot": 2302,
            },
        ]

        conveyance.culvert_size_table = pd.DataFrame(conveyance.culvert_size_table)
        culvert_cost = [115, 185, 265, 350, 525, 800, 1100, 1450]
        conveyance.culvert_size_table["cost_per_foot"] = culvert_cost
        conveyance.trapezoidal_channel_table = pd.DataFrame(conveyance.trapezoidal_channel_table)

        conveyance.culvert_size_table = conveyance.culvert_size_table[
            conveyance.culvert_size_table["flow_capacity_gpm"] >= self.peak_flow_rate_gpm
        ].iloc[0]
        conveyance.trapezoidal_channel_table = conveyance.trapezoidal_channel_table[
            conveyance.trapezoidal_channel_table["flowrate_gpm"] >= self.peak_flow_rate_gpm
        ].iloc[0]
        self.conveyance = conveyance

    def sediment_removal_pond(self):
        class SedimentRemovalPond:
            pass

        df = pd.DataFrame(
            columns=["Fine Silt", "Medium Silt"],
            index=[
                "Peak Storm Flow Rate (gpm)",
                "Channel Water Depth/Pond Depth (ft)",
                "Target Particle Size (mm)",
                "Required residence time for 0.4 inch Fall ((in/min)",
                "Number of 0.4in Falls in Depth",
                "Total time for total pond depth (min)",
                "Required sediment trap volume (gal)",
                "Required sediment trap volume (cf)",
                "Sediment Trap Water Depth",
                "Sediment Trap Footprint (sf)",
                "Sediment Trap Footprint (ac)",
                "Side length of square trap (ft)",
            ],
        )

        df.loc["Peak Storm Flow Rate (gpm)"] = self.peak_flow_rate_gpm
        df.loc["Channel Water Depth/Pond Depth (ft)"] = 36
        df.loc["Target Particle Size (mm)"] = [0.01, 0.03]
        df.loc["Required residence time for 0.4 inch Fall ((in/min)"] = [3.4, 0.38]
        df.loc["Number of 0.4in Falls in Depth"] = 90
        df.loc["Total time for total pond depth (min)"] = [90 * 3.4, 90 * 0.38]
        df.loc["Required sediment trap volume (gal)"] = (
            df.loc["Total time for total pond depth (min)"] * self.peak_flow_rate_gpm
        )
        df.loc["Required sediment trap volume (cf)"] = df.loc["Required sediment trap volume (gal)"] / 7.48
        df.loc["Sediment Trap Water Depth (ft)"] = 3
        df.loc["Sediment Trap Footprint (sf)"] = (
            df.loc["Required sediment trap volume (cf)"] / df.loc["Sediment Trap Water Depth (ft)"]
        )
        df.loc["Sediment Trap Footprint (ac)"] = df.loc["Sediment Trap Footprint (sf)"] / 43560
        df.loc["Side length of square trap (ft)"] = np.sqrt(df.loc["Sediment Trap Footprint (sf)"].astype(float))

        self.sediment_removal_pond_calculations = df
        self.sediment_removal_pond_area_acres = df.loc["Sediment Trap Footprint (ac)"][self.sediment_type]

    def contaminant_filters(self):
        """Cartridge Flow Rate and Requirements by Diameter."""
        cartridge_df = pd.DataFrame(
            {"12-inch Diameter": [5.0, 0.0, 0], "18-inch Diameter": [7.5, 0.0, 0], "27-inch Diameter": [11.3, 0.0, 0]},
            index=["Cartridge Flow Rate (gpm)", "Reduced Peak Flowrate (gpm)", "Number of Cartridges Required"],
        )

        cartridge_df.loc["Reduced Peak Flowrate (gpm)"] = self.peak_flow_rate_gpm * 0.12
        cartridge_df.loc["Number of Cartridges Required"] = (
            cartridge_df.loc["Reduced Peak Flowrate (gpm)"] / cartridge_df.loc["Cartridge Flow Rate (gpm)"]
        )
        cartridge_df.loc["Number of Cartridges Required"] = np.ceil(cartridge_df.loc["Number of Cartridges Required"])

        self.cartridge_df = cartridge_df

    def pump_conveyance_to_sediment_removal_pond(self):
        Q = self.peak_flow_rate_gpm * 0.002228009
        velocity = 5
        area = Q / velocity
        diameter = 2 * np.sqrt(area / np.pi)

        class Pump:
            pass

        pump = Pump()
        pump.diameter_inches = diameter * 12
        pump.velocity = velocity

        self.pump_to_storage_pond = pump

    def buried_pipeline_cost(self):
        """Pipe diameter lookup table based on design flow rate (gpm)."""
        pipe_diameter_df = pd.DataFrame(
            {
                "Design gpm": [500, 1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000, 11000],
                "Diameter": [6, 10, 14, 16, 20, 20, 24, 24, 24, 30, 30, 30],
            },
        )

        pipe_diameter_df["$ per foot"] = pipe_diameter_df["Diameter"] * 3.6

        mask = pipe_diameter_df["Diameter"] >= self.pump_to_storage_pond.diameter_inches
        pipe_diameter_df = pipe_diameter_df[mask].iloc[0]
        self.pipe_to_storage_pond = pipe_diameter_df

    def storage_pond(self):
        class StoragePond:
            pass

        storage_pond = StoragePond()

        storm_volume = self.hydro.total_storm_volume_gals
        storage_pond.depth_ft = 5
        storage_pond.freeboard_ft = 2
        storage_pond.volume_ft3 = storm_volume * 0.133681
        storage_pond.area_ft2 = storage_pond.volume_ft3 / storage_pond.depth_ft
        storage_pond.side_length_ft = np.sqrt(storage_pond.area_ft2)
        storage_pond.area_acres = storage_pond.area_ft2 / 43560.0

        self.storage_pond = storage_pond

    def dry_wells_infiltration(self):
        df = pd.DataFrame(columns=["Well Diameter (ft)"])
        df["Well Diameter (ft)"] = [4, 5, 6]
        df["Well Depth (ft)"] = [103, 104, 105]
        df["Well Volume (ft3)"] = df["Well Depth (ft)"] * (df["Well Diameter (ft)"] ** 2) * np.pi / 4
        side_area = 2 * np.pi * df["Well Diameter (ft)"] / 2 * 3.0
        df["Well Surface Area (ft2)"] = df["Well Diameter (ft)"] * np.pi * df["Well Diameter (ft)"] / 4.0
        df["Well Surface Area (in2)"] = df["Well Surface Area (ft2)"] * 144.0

        infil_rate_in_per_hr = self.dry_well_infiltration_rate_in_per_hr
        df["Well Capacity (in3/hr)"] = df["Well Surface Area (in2)"] * infil_rate_in_per_hr
        df["Well Capacity (gal/hr)"] = df["Well Capacity (in3/hr)"] / 231.0
        df["Well Capacity (gpm)"] = df["Well Capacity (gal/hr)"] / 60.0

        # Always use geohydro_rules dry-well count (DSS / decision graph), not a
        # separate capacity-based recount from transfer rate ÷ well capacity.
        try:
            n_wells = float(self.number_of_dry_wells or 0)
        except (TypeError, ValueError):
            n_wells = 0.0
        if not np.isfinite(n_wells) or n_wells < 0:
            n_wells = 0.0
        df["Number of Wells Required"] = n_wells
        df["Infiltration Rate (gal/day)"] = df["Well Capacity (gpm)"] * df["Number of Wells Required"] * 24 * 60

        df["Time to Drain (days)"] = self.hydro.total_storm_volume_gals / df["Infiltration Rate (gal/day)"]

        self.dry_wells_infiltration_calculations = df

    def injection_wells_infiltration(self):
        df = pd.DataFrame(
            columns=[
                "Transfer Rate (gpm)",
                "Number of Injection Wells",
                "Total Transfer Rate (gpm)",
                "Time to Drain (days)",
            ],
        )

        df.loc["Transfer Rate (gpm)"] = self.injection_well_transfer_rate_gpm
        df.loc["Number of Injection Wells"] = self.number_of_injection_wells
        df.loc["Total Transfer Rate (gpm)"] = df.loc["Transfer Rate (gpm)"] * df.loc["Number of Injection Wells"]
        df.loc["Time to Drain (days)"] = (
            self.hydro.total_storm_volume_gals / df.loc["Total Transfer Rate (gpm)"] / 24 / 60
        )
        self.injection_wells_infiltration_calculations = df

    def infiltration_basin(self):
        df = pd.DataFrame(index=[0])
        df.loc[0, "Basin Depth (ft)"] = 5
        df.loc[0, "Basin Area (sf)"] = self.hydro.total_storm_volume_gals * 0.133681 / df.loc[0, "Basin Depth (ft)"]
        df.loc[0, "Side Length (ft)"] = np.sqrt(df.loc[0, "Basin Area (sf)"])
        df.loc[0, "infil_rate (in/hr)"] = self.basin_soil_type_infiltration_rate_in_per_hr
        df.loc[0, "Time to Drain (days)"] = (df.loc[0, "Basin Depth (ft)"] * 12) / (
            df.loc[0, "infil_rate (in/hr)"] * 24
        )
        self.infiltration_basin_calculations = df

    def capital_costs(self):
        columns = ["Category", "Item", "Unit", "Unit Cost $", "Number of Units"]
        df = pd.DataFrame(columns=columns)

        # ======== collection point and site preparation ========
        # Flow capture structure and diversion pump are always included
        # (no longer user-selectable on the Engineering tab).
        # Rough grading is listed under INFILTRATION (below).
        irow = 0
        flow_capture_values = [
            "flow_capture_structure",
            "pump_used",
            "rough_grading",
        ]
        dash_storage.set_data("flow_capture_values", flow_capture_values)

        # ======== flow capture structure ========
        unit_price = 10000
        df.loc[irow] = ["COLLECTION BASIN PREPARATION", "Flow Capture Structure", "LS", unit_price, 1.0]

        # ======== pump is used to divert water ========
        irow += 1
        unit_price = 50000
        df.loc[irow] = ["COLLECTION BASIN PREPARATION", "Pump", "LF", unit_price, 1.0]

        # ======== conveyance to recharge site ========
        conveyance_method = dash_storage.get_data("conveyance_method")
        legacy = {
            "trapezoidal": "gravity_ditch",
            "pipeline": "gravity_pipeline",
            "pumped": "pumped_pipeline",
        }
        conveyance_method = legacy.get(conveyance_method, conveyance_method)
        dist = self.distance_collection_to_sediment_pond_ft

        if conveyance_method == "gravity_ditch":
            irow += 1
            df.loc[irow] = [
                "CONVEYANCE TO RECHARGE SITE",
                "Gravity Flow in Ditch/Channel",
                "LF",
                93,
                dist,
            ]
        elif conveyance_method == "gravity_pipeline":
            irow += 1
            df.loc[irow] = [
                "CONVEYANCE TO RECHARGE SITE",
                "Gravity Flow in Pipeline",
                "LF",
                72,
                dist,
            ]
        elif conveyance_method == "pumped_pipeline":
            irow += 1
            df.loc[irow] = [
                "CONVEYANCE TO RECHARGE SITE",
                "Pipeline",
                "LF",
                60,
                dist,
            ]
        elif conveyance_method == "pumped_ditch":
            # Hybrid: channel civil + pump package
            irow += 1
            df.loc[irow] = [
                "CONVEYANCE TO RECHARGE SITE",
                "Pumped into Ditch/Channel — Civil",
                "LF",
                100,
                dist,
            ]
            irow += 1
            df.loc[irow] = [
                "CONVEYANCE TO RECHARGE SITE",
                "Pumped into Ditch/Channel — Pump Package",
                "LF",
                307,
                dist,
            ]

        # ======== sediment removal pond ========
        needed = dash_storage.get_data("sediment_removal_needed")
        if needed is None:
            # Legacy invert: remove_sediment_removal_pond True → not needed
            remove_legacy = dash_storage.get_data("remove_sediment_removal_pond")
            needed_yes = not bool(remove_legacy)
        else:
            needed_yes = needed == "yes"

        if needed_yes:
            trash_rack_price = 10000
            pond_unit_price = 500000
            dash_storage.set_data("sediment_pond_values", ["trash_rack"])
        else:
            trash_rack_price = 0
            pond_unit_price = 0
            dash_storage.set_data("sediment_pond_values", [])

        irow += 1
        df.loc[irow] = ["SEDIMENT REMOVAL POND", "Trash Rack", "LS", trash_rack_price, 1]

        pond_area = self.sediment_removal_pond_area_acres
        irow += 1
        df.loc[irow] = ["SEDIMENT REMOVAL POND", self.sediment_type, "Acre", pond_unit_price, pond_area]

        # ==== storage (+ automatic pumped conveyance to storage at 500 ft)
        storage_needed = dash_storage.get_data("storage_needed")
        storage_pond_values = dash_storage.get_data("storage_pond_values") or []
        if storage_needed in ("yes", "no"):
            storage = storage_needed == "yes"
        else:
            storage = "storage_pond_construction" in storage_pond_values

        if storage:
            dash_storage.set_data("storage_pond_values", ["storage_pond_construction"])
            dash_storage.set_data(
                "pumped_storage_values",
                [
                    "pumping_bag_filter_cost",
                    "controls",
                    "electrical_system",
                ],
            )
            dash_storage.set_data("distance_to_storage_pond_ft", 500.0)
            self.distance_sediment_to_storage_pond_ft = 500.0
        else:
            dash_storage.set_data("storage_pond_values", [])
            dash_storage.set_data("pumped_storage_values", [])

        # Pumping / controls / electrical under PUMPED CONVEYANCE.
        # Base package = 1 (infiltration). Each of storage pond and sediment
        # removal pond adds one more package → 2× or 3× when both are present.
        pumped_pkg_count = 1 + int(bool(storage)) + int(bool(needed_yes))
        irow += 1
        df.loc[irow] = ["PUMPED CONVEYANCE", "Pumping and Bag Filter Cost", "LS", 100000, pumped_pkg_count]
        irow += 1
        df.loc[irow] = ["PUMPED CONVEYANCE", "Controls", "LS", 50000, pumped_pkg_count]
        irow += 1
        df.loc[irow] = ["PUMPED CONVEYANCE", "Electrical System", "LS", 20000, pumped_pkg_count]

        if storage:
            unit_price = 200000
        else:
            unit_price = 0
        irow += 1
        df.loc[irow] = [
            "STORAGE POND",
            "Pond construction cost",
            "Acre",
            unit_price,
            self.storage_pond.area_ft2 / 43560.0,
        ]

        # ==== infiltration site (pipeline only; pump/controls/electrical consolidated above)
        pumped_infiltration_values = [
            "infiltration_pipeline_cost",
        ]
        dash_storage.set_data("pumped_infiltration_values", pumped_infiltration_values)

        unit_price = 72
        irow += 1
        df.loc[irow] = ["PUMPED CONVEYANCE TO INFILTRATION SITE", "Pipeline Cost", "LF", unit_price, 500]

        # Rough grading / grubbing belongs with infiltration works (not collection).
        irow += 1
        unit_price = 1500
        df.loc[irow] = ["INFILTRATION", "Rough Grading/Grubbing in Field", "acres", unit_price, 1.0]

        unit_price = 75000
        irow += 1
        irow_dry_well = irow
        try:
            n_dry = float(self.number_of_dry_wells or 0)
        except (TypeError, ValueError):
            n_dry = 0.0
        df.loc[irow] = ["INFILTRATION", "Dry Well Cost", "LF", unit_price, n_dry]
        unit_price = 400000
        irow += 1
        irow_injection_wells = irow
        df.loc[irow] = ["INFILTRATION", "Injection Wells", "EA", unit_price, self.number_of_injection_wells]

        # Distribution piping: $60,000/EA × max(n_wells − 1, 0); separate rows
        # because injection and dry-well counts differ.
        dist_piping_unit_cost = 60000

        def _wells_minus_one(n_wells):
            try:
                n = float(n_wells or 0)
            except (TypeError, ValueError):
                return 0.0
            if not np.isfinite(n) or n <= 1:
                return 0.0
            return n - 1.0

        irow += 1
        irow_dist_piping_injection = irow
        df.loc[irow] = [
            "INFILTRATION",
            "Distribution Piping - Injection",
            "EA",
            dist_piping_unit_cost,
            _wells_minus_one(self.number_of_injection_wells),
        ]
        irow += 1
        irow_dist_piping_dry = irow
        df.loc[irow] = [
            "INFILTRATION",
            "Distribution Piping - Dry Well",
            "EA",
            dist_piping_unit_cost,
            _wells_minus_one(self.number_of_dry_wells),
        ]
        irow += 1
        irow_infiltration_basin = irow
        unit_price = 200000
        df.loc[irow] = [
            "INFILTRATION",
            "Infiltration Basin",
            "Acre",
            unit_price,
            self.infiltration_basin_calculations["Basin Area (sf)"][0] / 43560.0,
        ]

        # Catalog Unit Cost $ stays fixed for display. Method columns zero out
        # rows that do not apply to that recharge option (do not mutate Unit Cost $).
        line_cost = df["Unit Cost $"] * df["Number of Units"]
        method_exclude = {
            "Spreading Pond": [
                irow_dry_well,
                irow_injection_wells,
                irow_dist_piping_injection,
                irow_dist_piping_dry,
            ],
            "Injection Wells": [
                irow_dry_well,
                irow_dist_piping_dry,
                irow_infiltration_basin,
            ],
            "Dry Wells": [
                irow_injection_wells,
                irow_dist_piping_injection,
                irow_infiltration_basin,
            ],
        }

        for recharge_method in ["Spreading Pond", "Injection Wells", "Dry Wells"]:
            name = recharge_method + " Cost ($)"
            col = line_cost.copy()
            for i_ex in method_exclude[recharge_method]:
                col.loc[i_ex] = 0.0
            df[name] = col
            subtotal = df[name].sum()
            df.loc["Subtotal", name] = subtotal
            df.loc["Project Management (10%)", name] = subtotal * 0.1
            df.loc["Permitting (15%)", name] = subtotal * 0.15
            df.loc["Engineering (18%)", name] = subtotal * 0.18

            df.loc["subtotal_with_fees", name] = (
                df.loc["Subtotal", name]
                + df.loc["Project Management (10%)", name]
                + df.loc["Permitting (15%)", name]
                + df.loc["Engineering (18%)", name]
            )
            df.loc["Capital Total Cost", name] = df.loc["subtotal_with_fees", name]

        # df.loc['subtotal_with_fees', 'Total Cost ($)'] = (
        #     df.loc['Subtotal', 'Total Cost ($)'] +
        #     df.loc['Project Management', 'Total Cost ($)'] +
        #     df.loc['Permitting', 'Total Cost ($)'] +
        #     df.loc['Legal Fees', 'Total Cost ($)'] +
        #     df.loc['Engineering', 'Total Cost ($)'] +
        #     df.loc['Construction Admin and Oversight', 'Total Cost ($)']
        # )
        # df.loc['Contingency', 'Total Cost ($)'] = (
        #     df.loc['subtotal_with_fees', 'Total Cost ($)'] * 0.3
        # )
        # df.loc['Capital Total Cost', 'Total Cost ($)'] = (
        #     df.loc['subtotal_with_fees', 'Total Cost ($)'] +
        #     df.loc['Contingency', 'Total Cost ($)']
        # )
        self.capital_costs_calculations = df

    def maintenance_costs(self):
        """Annual O&M = 5% of each option's Capital Total Cost."""
        maint_fraction = 0.05
        columns = ["Category", "Item", "Unit", "Unit Cost $", "Number of Units"]
        df = pd.DataFrame(columns=columns)
        df.loc[0] = [
            "ANNUAL O&M",
            "Maintenance (5% of capital)",
            "LS",
            maint_fraction,
            1.0,
        ]
        for recharge_method in ["Spreading Pond", "Injection Wells", "Dry Wells"]:
            name = recharge_method + " Maintenance Cost ($)"
            cap_col = recharge_method + " Cost ($)"
            try:
                capital = float(self.capital_costs_calculations.loc["Capital Total Cost", cap_col])
            except (KeyError, TypeError, ValueError):
                capital = 0.0
            if not np.isfinite(capital) or capital < 0:
                capital = 0.0
            maint = capital * maint_fraction
            df[name] = 0.0
            df.loc[0, name] = maint
            df.loc["Subtotal Maintenance Cost ($)", name] = maint
            df.loc["Annual Grand Maintenance Cost", name] = maint

        self.maintenance_costs_calculations = df

    def net_present_value(self):
        df = pd.DataFrame()
        df.index = range(1, 21)
        df.index.name = "Year"
        for recharge_method in ["Spreading Pond", "Injection Wells", "Dry Wells"]:
            name1 = recharge_method + " Cost ($)"
            capital_cost = self.capital_costs_calculations.loc["Capital Total Cost", name1]
            name2 = recharge_method + " Maintenance Cost ($)"

            annual_maintenance_cost = self.maintenance_costs_calculations.loc["Annual Grand Maintenance Cost", name2]
            annual_esclation_rate = 2.99 / 100
            npv_discount_rate = 5.01 / 100

            inflation_adjusted_maintenance_cost = []
            pv_costs = 0
            net_value = []
            for i in range(1, 21):
                if i == 1:
                    inflation_adjusted_maintenance_cost.append(annual_maintenance_cost)
                    pv_costs = pv_costs + (annual_maintenance_cost / (1 + npv_discount_rate) ** i)
                    net_value.append(pv_costs + capital_cost)
                    continue
                previous_cost = inflation_adjusted_maintenance_cost[i - 2]
                current_cost = previous_cost + previous_cost * annual_esclation_rate
                inflation_adjusted_maintenance_cost.append(current_cost)
                pv_costs = pv_costs + (current_cost / (1 + npv_discount_rate) ** i)
                net_value.append(pv_costs + capital_cost)
            pv_costs = pv_costs + capital_cost
            name3 = recharge_method + " Net Present Value ($)"
            df[name3] = net_value
        self.net_present_value_calculations = df


# if __name__ == "__main__":
#     cost_calculator = CostCalculator(
#         water_source="stormwater", storm_design_depth=1.8,
#         drainage_basin_area_acres=35,
#         total_storm_volume_af=6.52,
#         basin_soil_type_infiltration_rate_in_per_hr=0.2,
#         peak_flow_rate_gpm=3958,
#         fine_sediment_removal_goal="Fine Silt",
#         distance_collection_to_sediment_pond_ft=2640,
#         distance_sediment_to_storage_pond_ft=2640,
#         dry_well_infiltration_rate_in_per_hr=5,
#         dry_well_transfer_rate_gpm=50,
#         injection_well_transfer_rate_gpm=50,
#         number_of_injection_wells=5,
#         collection_to_sediment_removal__conveyance_method="trapezoidal",
#         dry_well_diameter_ft=6,
#         recharge_method="dry_well"
#     )
#     cost_calculator.calculate_cost()
