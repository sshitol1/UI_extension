import omni.ext
import omni.ui as ui
import pandas as pd
from omni.ui import color as cl
import math

class MyExtension(omni.ext.IExt):

    RPM1_PERCENT = 1  # Base RPM percentage for calculations
    CFM1 = 29081      # PW170 CFM value
    HP1_PER_CRAH = 13.5  # PW170 total power in kW

    vendor_data = [
    {
        "Vendor": "Vertiv",
        "CDU Model": "AHU FA069HC",
        "Net Total Capacity (kW)": 252.4,
        "Inlet Water Temperature (°C)": 18,
        "Outlet Water Temperature (°C)": 25,
        "Primary Max Flow Rate (LPM)": 548.4,
        "Air CFM": 40600,
        "Total Power (kW)": 15,
        "Price ($)": None  # Add price here if needed
    },
    {
        "Vendor": "Vertiv",
        "CDU Model": "AHU FA096HC",
        "Net Total Capacity (kW)": 351.7,
        "Inlet Water Temperature (°C)": 18,
        "Outlet Water Temperature (°C)": 25,
        "Primary Max Flow Rate (LPM)": 761.4,
        "Air CFM": 56800,
        "Total Power (kW)": 19.5,
        "Price ($)": None  # Add price here if needed
    },
    {
        "Vendor": "Vertiv",
        "CDU Model": "PW170",
        "Net Total Capacity (kW)": 233,
        "Inlet Water Temperature (°C)": 18,
        "Outlet Water Temperature (°C)": 38,
        "Primary Max Flow Rate (LPM)": 175,
        "Air CFM": 29081,
        "Total Power (kW)": 13.5,
        "Price ($)": 74000
    }
]
    water_rho_cp = 4193
    # Quadratic System Curve coefficients based on pod type and CDUs
    QSC_COEFFICIENTS = {
        "576 GPU DGX GB200 Super Pod": {
            1: {"a": 0.00007100, "b": 0.02422900, "c": -0.39533800},
            2: {"a": 0.0028300, "b": 0.04845800, "c": -0.39533800}
        },
        "1152 GPU DGX GB200 Super Pod": {
            3: {"a": 0.00018600, "b": 0.04140900, "c": -0.55493400},
            4: {"a": 0.00033000, "b": 0.05521200, "c": -0.55493400}
        }
    }
    HP1 = 13.7  # Constant power (kW) for HP1
    rpm1 = 1  # Treat rpm1 as a constant
        # XDU 1350 PQ curve constants
    XDU_PQC = {
        "a": -0.000234,
        "b": 0.092063,
        "c": 476.456770
    }

    PRIMARY_DELTA_TEMP = 10  # in °C
    MAX_SECONDARY_FLOW_RATE_CDU = 1200  # in LPM
    NOMINAL_COOLING_CAPACITIES = {
        "XDU1350": 1367,
        "MCDU60": 1200,
        "MCDU50": 1725,
        "XDU600": 600,
        "XDU070": 55,
        "MHDU5900": 1368,
        "MHDU5910": 1200
    }
    # Constant for Rho * C Secondary Flow in kJ/(C * m^3)
    RHO_C_SECONDARY_FLOW = 4120  # in kJ/(C * m^3)

    # Constants for fixed air flow rates (in CFM) for Management and Network racks
    AIR_FLOW_RATE_MANAGEMENT_RACK = 3900
    AIR_FLOW_RATE_NETWORK_RACK = 3900

    POWER_PER_RACK = {
        "GB200_NVL72": 132,
        "Management": 30,
        "Networking": 30
    }

    # Air cooling capacity per rack in kW
    AIR_COOLING_CAPACITY_PER_RACK = {
        "GB200_NVL72": 17.16,
        "Management": 30,
        "Networking": 30
    }

    # Rack configuration per pod type
    POD_RACK_COUNTS = {
        "288 GPU DGX GB200 Super Pod": {"GB200_NVL72": 4, "Management": 2, "Networking": 3},
        "576 GPU DGX GB200 Super Pod": {"GB200_NVL72": 8, "Management": 4, "Networking": 6},
        "1152 GPU DGX GB200 Super Pod": {"GB200_NVL72": 16, "Management": 8, "Networking": 12}
    }
    def on_startup(self, ext_id):
        print("My Extension has started")
        self._window = ui.Window("Data Center Configuration", width=800, height=800)

        self.chillers_data = pd.read_csv(
            r"C:\Users\Soham\kit-app-template-main\ui_for_ov\exts\ui_for_ov\docs\Chillers.csv", # or try "Windows-1252"
        )
        self.fws_design_temperature_air = None

        # print(self.chillers_data.columns)
            # If you only need a subset of columns, select them directly
        required_columns = [
            'Model', 'TWOUT', 'TA ', 'Cooling Cpacity',
            'Power Input', 'Fluid Flow rate  (l/s)',
            'Fluid Pressure Drop (kPa)', 'Evaporator'
        ]

        # Select only the necessary columns if they exist in the loaded data
        self.chillers_data = self.chillers_data[required_columns]

                # Load data
        self.climate_data = pd.read_csv(r"C:\Users\Soham\kit-app-template-main\ui_for_ov\exts\ui_for_ov\docs\TCO_new.csv")
        self.climate_data.columns = ['Region', 'Country', 'State', 'City', 'Dry Bulb', 'Wet Bulb',
                                'Dew Point', 'Humidity Ratio']
        self.climate_data['City'] = self.climate_data['City'].astype(str).str.strip()
        self.unique_cities = sorted(self.climate_data['City'].unique().tolist())

        self.drt_bulb = None
                # Initialize temperature ranges dynamically using a dictionary
        self.temperature_ranges = {
            "A1": list(range(15, 33)),
            "A2": list(range(10, 36)),
            "A3": list(range(5, 41)),
            "A4": list(range(5, 46)),
            "B": list(range(5, 37)),
            "C": list(range(5, 42)),
            "H1": list(range(15, 27)),
            "Default": list(range(15, 34))
        }

        # Temperature ranges for liquid cooling options
        self.liquid_cooling_temp_ranges = {
            "W17": list(range(2, 18)),
            "W27": list(range(2, 28)),
            "W32": list(range(2, 33)),
            "W40": list(range(2, 41)),
            "W45": list(range(2, 46)),
            "W+": list(range(2, 50)),
            "Default": list(range(15, 34))
        }

        self.liquid_cooling_options = ["Select Data Center Liquid Cooling option","W17", "W27", "W32", "W40", "W45", "W+"]

        # Define configuration options
        self.it_product_options = ["GB200_NVL72", "GB200_NVL36"]
        self.pod_options = ["288 GPU DGX GB200 Super Pod", "576 GPU DGX GB200 Super Pod", "1152 GPU DGX GB200 Super Pod"]
        self.data_center_class_options = ["Select Data Center Air Cooling option","A1", "A2", "A3", "A4", "B", "C", "H1"]
        self.cdu_options = ["Liquid to Liquid", "Liquid to Air"]
                # Define options for ComboBoxes
        self.air_supply_options = [str(x) for x in range(15, 33)]
        self.tcs_liquid_options = [str(x) for x in range(17, 46)]
        self.fws_air_options = [str(x) for x in range(5,46)]
        self.fws_liquid_options = [str(x) for x in range(5,46)]
        self.current_cdu_type = self.cdu_options[0]


        # Define consistent styles
        self.STYLES = {
            "main_container": {
                "padding": 20,
                "spacing": 20,
                "background_color": cl("#76B900"),  # Near white for a clean look
            },
            "section_frame": {
                "border_radius": 5,
                "border_width": 2,
                "border_color": cl("#CCCCCC"),  # Light gray for subtle separation
                "margin": 10,
                "padding": 15,
                "background_color": cl("#FFFFFF"),  # Pure white for contrast
            },
            "title": {
                "font_size": 32,
                "font_weight": "bold",
                "color": cl("#76B900"),  # NVIDIA green for primary headers
                "alignment": ui.Alignment.CENTER,
            },
            "section_title": {
                "font_size": 20,
                "font_weight": "bold",
                "color": cl("#000000"),
                "margin": 15,
            },
            "label": {
                "font_size": 18,
                "color": cl("#000000"),  # Dark gray for readability against white background
            },
            "value_label": {
                "font_size": 18,
                "color": cl("#000000"),  # Dark green for highlighted values
                "font_weight": "bold",
            },
            "dynamic_value": {  # For values that change
                "font_size": 18,
                "color": cl("#1ABC9C"),  # Teal for updated values
                "font_weight": "bold",
            },
            "highlight_label": {
                "font_size": 18,
                "color": cl("#000000"),  # Dark green for highlighted important labels
                "font_weight": "bold",
                "alignment": ui.Alignment.LEFT,
                "margin_top": 15,
            },
            "combo_box": {  # Style for ComboBox elements
                "font_size": 16,
                "color": cl("#808080"),  # Darker text color for dropdown items
                "background_color": cl("#FFFFFF"),  # Light gray for dropdown background
            },
            "input_container": {
                "margin": 10,
                "spacing": 10,
                "background_color": cl("#FFFFFF"),  # Clean white for input areas
            },
            "separator": {
                "margin_top": 15,
                "margin_bottom": 15,
                "color": cl("#808080"),  # Subtle separator for sections
            },
            "footer": {
                "font_size": 12,
                "color": cl("#333333"),  # Consistent with label color
                "alignment": ui.Alignment.CENTER,
                "margin_top": 20,
            },
        }



        with self._window.frame:
            with ui.ScrollingFrame():
                with ui.VStack(style=self.STYLES["main_container"]):
                    try:

                        # Header Section
                        ui.Label("Data Center Configuration", style=self.STYLES["title"])
                        ui.Spacer(height=20)

                        # Location Section
                        with ui.CollapsableFrame("Location Information", style=self.STYLES["section_frame"]):
                            with ui.VStack(style=self.STYLES["input_container"]):
                                with ui.HStack(height=30):
                                    ui.Label("Select City:", width=100, style=self.STYLES["label"])
                                    self.city_menu = ui.ComboBox(0, *self.unique_cities, style = self.STYLES["combo_box"])
                                self.country_label = ui.Label("Country: ", style=self.STYLES["value_label"])
                                self.state_label = ui.Label("State: ", style=self.STYLES["value_label"])

                        # Climate Information Section
                        with ui.CollapsableFrame("Climate Information", style=self.STYLES["section_frame"]):
                            with ui.VStack(style=self.STYLES["input_container"]):
                                self.dry_bulb_label = ui.Label("Dry Bulb: ", style=self.STYLES["value_label"])
                                self.wet_bulb_label = ui.Label("Wet Bulb: ", style=self.STYLES["value_label"])
                                self.dew_point_label = ui.Label("Dew Point: ", style=self.STYLES["value_label"])
                                self.humidity_ratio_label = ui.Label("Humidity Ratio: ", style=self.STYLES["value_label"])

                        # IT Product Configuration Section
                        with ui.CollapsableFrame("IT Product Configuration", style=self.STYLES["section_frame"]):
                            with ui.VStack(style=self.STYLES["input_container"]):
                                with ui.HStack(height=30):
                                    ui.Label("IT Product:", width=150, style=self.STYLES["label"])
                                    self.it_product_menu = ui.ComboBox(0, *self.it_product_options, style = self.STYLES["combo_box"])

                                with ui.HStack(height=30):
                                    ui.Label("POD:", width=150, style=self.STYLES["label"])
                                    self.pod_menu = ui.ComboBox(0, *self.pod_options, style = self.STYLES["combo_box"])

                                with ui.HStack(height=30):
                                    ui.Label("Number of Pods:", width=150, style=self.STYLES["label"])
                                    self.num_pods_field = ui.StringField()

                                with ui.VStack(style=self.STYLES["input_container"]):
                                    self.total_power_label = ui.Label("Total Power: N/A", style=self.STYLES["highlight_label"])
                                    self.total_air_cooling_label = ui.Label("Total Air Cooling Capacity: N/A", style=self.STYLES["highlight_label"])
                                    self.total_liquid_cooling_label = ui.Label("Total Liquid Cooling Capacity: N/A", style=self.STYLES["highlight_label"])


                        # Data Center Class Section
                        with ui.CollapsableFrame("Data Center Specifications", style=self.STYLES["section_frame"]):
                            with ui.VStack(style=self.STYLES["input_container"]):
                                with ui.HStack(height=30):
                                    ui.Label("Data Center Class:", width=260, style=self.STYLES["label"])
                                    self.class_menu = ui.ComboBox(0, *self.data_center_class_options, style = self.STYLES["combo_box"])

                                    # New Liquid Cooling Options
                                with ui.HStack(height=30):
                                    ui.Label("Data Center Class Liquid Cooling:", width=150, style=self.STYLES["label"])
                                    self.liquid_cooling_menu = ui.ComboBox(0, *self.liquid_cooling_options, style = self.STYLES["combo_box"])


                        # Cooling Specification Section
                        with ui.CollapsableFrame("Cooling Specification", style=self.STYLES["section_frame"]):
                            with ui.VStack(style=self.STYLES["input_container"]):

                                                                # TCS container
                                # ComboBox for Air Supply Temperature
                                with ui.HStack(height=30) as self.air_supply_container:
                                    ui.Label("Air Supply Temperature:", width=150, style=self.STYLES["label"])
                                    self.air_supply_menu = ui.ComboBox(0, *self.air_supply_options, style = self.STYLES["combo_box"])  # Use options list

                                # ComboBox for TCS Liquid
                                with ui.HStack(height=30):
                                    ui.Label("TCS Liquid:", width=195, style=self.STYLES["label"])
                                    self.tcs_liquid_menu = ui.ComboBox(0, *self.tcs_liquid_options, style = self.STYLES["combo_box"])  # Use options list

                                # Display calculated airflow rate per pod
                                self.required_airflow_rate_label = ui.Label("Required Air Flow Rate per Pod (CFM): N/A", style=self.STYLES["highlight_label"])
                                self.required_liquid_flow_rate_label = ui.Label("Required Liquid Flow Rate per Pod (LPM): N/A", style=self.STYLES["highlight_label"])


                        # Facility Specification Section
                        with ui.CollapsableFrame(" Facility Specification", style=self.STYLES["section_frame"]):
                            with ui.VStack(style=self.STYLES["input_container"]):

                                # Container for fws_air_menu ComboBox
                                with ui.HStack(height=30) as self.fws_air_container:
                                    ui.Label("FWS Design Temp (Air):", width=210, style=self.STYLES["label"])
                                    self.fws_air_menu = ui.ComboBox(0, *self.fws_air_options, style = self.STYLES["combo_box"])  # Initial values
                                    ui.Label("°C", width=30)

                                # Container for fws_liquid_menu ComboBox
                                with ui.HStack(height=30) as self.fws_liquid_container:
                                    ui.Label("FWS Design Temp (Liquid):", width=150, style=self.STYLES["label"])
                                    self.fws_liquid_menu = ui.ComboBox(0, *self.fws_liquid_options, style = self.STYLES["combo_box"])  # Initial values
                                    ui.Label("°C", width=30)

                                with ui.HStack(height=30):
                                    ui.Label("CDU Type:", width=210, style=self.STYLES["label"])
                                    self.cdu_menu = ui.ComboBox(0, *self.cdu_options)
                                    self.cdu_menu.model.get_item_value_model().add_value_changed_fn(self.on_cdu_type_selected)

                        # Facility Equipment Options Section
                        with ui.CollapsableFrame("Facility Equipment Options", style=self.STYLES["section_frame"]):
                            with ui.VStack(style=self.STYLES["input_container"]):
                                                            # Update other calculated value labels
                                # self.total_power_label = ui.Label("Total Power: N/A", style=self.STYLES["highlight_label"])
                                # self.total_air_cooling_label = ui.Label("Total Air Cooling Capacity: N/A", style=self.STYLES["highlight_label"])
                                # self.total_liquid_cooling_label = ui.Label("Total Liquid Cooling Capacity: N/A", style=self.STYLES["highlight_label"])
                                self.total_cdus_label = ui.Label("Total CDUs: N/A", style=self.STYLES["highlight_label"])
                                self.primary_flow_rate_per_cdu_label = ui.Label("Primary Flow Rate per CDU (LPM): N/A", style=self.STYLES["highlight_label"])
                                self.secondary_flow_rate_per_cdu_label = ui.Label("Secondary Flow Rate per CDU (LPM): N/A", style=self.STYLES["highlight_label"])
                                self.primary_flow_rate_per_pod_label = ui.Label("Primary Flow Rate per Pod (LPM): N/A", style=self.STYLES["highlight_label"])

                        with ui.CollapsableFrame("Facility Equipment Options", style=self.STYLES["section_frame"]):
                            # Add a dropdown for CDU selection (1-4)
                            with ui.VStack():
                                ui.Label("Select Number of CDUs:", width=200, style=self.STYLES["label"])
                                self.num_cdus_menu = ui.ComboBox(0, *[str(x) for x in range(1, 5)], style=self.STYLES["combo_box"])
                                self.num_cdus_menu.model.get_item_value_model().add_value_changed_fn(lambda model: self.update_pod_flowrate_and_curve())
                            with ui.VStack():
                                self.pod_flowrate_cdu_label = ui.Label("POD Flow Rate per CDU: N/A LPM", style=self.STYLES["highlight_label"])
                                self.cdu_hp2_label = ui.Label("HP2 (kW): N/A", style=self.STYLES["highlight_label"])
                                self.cdu_hp_per_pod_label = ui.Label("HP per Pod: N/A", style=self.STYLES["highlight_label"])
                                self.air_temperature_rise_label = ui.Label("Air Temperature Rise in Rack: Calculating...", style=self.STYLES["highlight_label"])
                                self.air_return_temperature_label = ui.Label("Air Return Temperature: Calculating...", style=self.STYLES["highlight_label"])
                                self.q_per_crah_label = ui.Label("Q per CRAH: Calculating...", style=self.STYLES["highlight_label"])
                                self.chilled_water_flow_rate_crah_label = ui.Label("Chilled Water Flow Rate per CRAH (LPM): Calculating...", style=self.STYLES["highlight_label"])
                                self.chilled_water_flow_rate_pod_label = ui.Label("Chilled Water Flow Rate per POD (LPM): Calculating...", style=self.STYLES["highlight_label"])
                                self.q_ac_per_pod_label = ui.Label("Q AC per POD (kW): Calculating...", style=self.STYLES["highlight_label"])
                                self.liquid_cooling_label1 = ui.Label("Liquid Cooling Option 1: Not Set", style=self.STYLES["value_label"])
                                self.liquid_cooling_label2 = ui.Label("Liquid Cooling Option 2: Not Set", style=self.STYLES["value_label"])
                                self.crah_hp1_label = ui.Label("HP1 PER CRAH: N/A", style=self.STYLES["highlight_label"])
                                self.crah_hp2_label = ui.Label("HP2 per CRAH: N/A", style=self.STYLES["highlight_label"])

                            # Initialize calculations based on default settings
                                    # Initial calculation and UI update
                                self.update_calculations()
                                self.update_flow_rates()

                                    # CRAH Labels
                                self.crah_labels = []
                                self.crah_label_vertiv_pw170 = ui.Label("Number of CRAHs for Vertiv PW170: Calculating...", style=self.STYLES["highlight_label"])

                        # Footer
                        ui.Label(
                            "💡 Select different options to see updated climate information",
                            style=self.STYLES["footer"]
                        )

                        # Event handlers
                        self.class_menu.model.get_item_value_model().add_value_changed_fn(
                            lambda model: self.update_air_supply_temperature_range()
                        )
                        self.city_menu.model.get_item_value_model().add_value_changed_fn(
                            lambda model: self.update_climate_info(self.unique_cities[model.as_int])
                        )
                        self.liquid_cooling_menu.model.get_item_value_model().add_value_changed_fn(
                            lambda model: self.update_air_supply_temperature_range()
                        )

                        self.fws_air_menu.model.get_item_value_model().add_value_changed_fn(lambda model: self.calculate_chilled_water_flow_rate_per_pod())
                        self.fws_air_menu.model.get_item_value_model().add_value_changed_fn(lambda model: self.calculate_chilled_water_flow_rate_per_crah())


                        # Event listener to update FWS Design Temp (Liquid) based on TCS Liquid selection
                        self.tcs_liquid_menu.model.get_item_value_model().add_value_changed_fn(
                            lambda model: self.update_fws_design_temperature_liquid(int(self.tcs_liquid_options[model.as_int]))
                        )

                        self.air_supply_menu.model.get_item_value_model().add_value_changed_fn(lambda model: self.update_fws_design_temperature_air(int(self.tcs_liquid_options[model.as_int])))
                        self.pod_menu.model.get_item_value_model().add_value_changed_fn(lambda model: self.calculate_total_power())
                        self.num_pods_field.model.add_value_changed_fn(lambda model: self.calculate_total_power())

                        self.pod_menu.model.get_item_value_model().add_value_changed_fn(lambda model: self.update_cooling_capacities())

                        # Attach to event listeners
                        # self.air_supply_menu.model.get_item_value_model().add_value_changed_fn(lambda model: self.update_flow_rates())
                        self.tcs_liquid_menu.model.get_item_value_model().add_value_changed_fn(lambda model: self.update_flow_rates())
                        self.tcs_liquid_menu.model.get_item_value_model().add_value_changed_fn(lambda model: self.update_calculations())

                                # Attach event listeners

                        self.fws_liquid_menu.model.get_item_value_model().add_value_changed_fn(lambda model: self.update_flow_rates())
                        self.fws_liquid_menu.model.get_item_value_model().add_value_changed_fn(lambda model: self.calculate_chilled_water_temperature_rise())
                        self.fws_air_menu.model.get_item_value_model().add_value_changed_fn(lambda model: self.calculate_chilled_water_temperature_rise())
                        self.fws_air_menu.model.get_item_value_model().add_value_changed_fn(lambda model: self.calculate_chilled_water_flow_rate_per_crah())
                        self.fws_air_menu.model.get_item_value_model().add_value_changed_fn(lambda model: self.calculate_chilled_water_flow_rate_per_pod())
                        self.fws_air_menu.model.get_item_value_model().add_value_changed_fn(lambda model: self.update_calculations())

                        self.tcs_liquid_menu.model.get_item_value_model().add_value_changed_fn(lambda model: self.update_flow_rates())

                        self.air_supply_menu.model.get_item_value_model().add_value_changed_fn(lambda model: self.update_calculations())
                        self.num_pods_field.model.add_value_changed_fn(lambda model: self.update_calculations())

                        self.cdu_menu.model.get_item_value_model().add_value_changed_fn(self.on_cdu_type_selected)

                        # Initial update
                        if self.unique_cities:
                            self.update_climate_info(self.unique_cities[0])

                    except Exception as e:
                        ui.Label(f"Error loading data: {str(e)}", style=self.STYLES["label"])

    def update_air_supply_temperature_range(self):
        try:
            # Get selected data center class and liquid cooling option
            selected_class = self.data_center_class_options[self.class_menu.model.get_item_value_model().as_int]
            selected_cooling = self.liquid_cooling_options[self.liquid_cooling_menu.model.get_item_value_model().as_int]

            # Determine ranges based on selections
            class_range = self.temperature_ranges.get(selected_class, [])
            cooling_range = self.liquid_cooling_temp_ranges.get(selected_cooling, [])

            # Handle cases based on selection states
            if selected_class == "Select Data Center Air Cooling option" and selected_cooling == "Select Data Center Liquid Cooling option":
                self.air_supply_container.clear()
                with self.air_supply_container:
                    ui.Label("Air Supply Temperature:", width=150, style=self.STYLES["label"])
                    self.air_supply_menu = ui.ComboBox(0, "Select")
                return

            elif selected_class != "Select Data Center Air Cooling option" and selected_cooling == "Select Data Center Liquid Cooling option":
                final_range = class_range

            elif selected_class == "Select Data Center Air Cooling option" and selected_cooling != "Select Data Center Liquid Cooling option":
                final_range = cooling_range

            else:
                min_temp = max(class_range[0], cooling_range[0])
                max_temp = min(class_range[-1], cooling_range[-1])
                final_range = list(range(min_temp, max_temp + 1))

            # Convert to °C format
            final_range_formatted = [f"{temp}°C" for temp in final_range]

            # Update `self.air_supply_options` with the new range
            self.air_supply_options = final_range_formatted

            # Update ComboBox with the new range
            self.air_supply_container.clear()
            with self.air_supply_container:
                ui.Label("Air Supply Temperature", width=150, style=self.STYLES["label"])
                self.air_supply_menu = ui.ComboBox(0, "Select", *self.air_supply_options)

            # Attach recalculation handler
            self.air_supply_menu.model.get_item_value_model().add_value_changed_fn(lambda model: self.update_calculations())

            print(f"Updated Air Supply Temperature range to: {final_range_formatted}")

        except Exception as e:
            print(f"Error updating Air Supply Temperature range: {str(e)}")

    def on_cdu_type_selected(self, model):
        """Event handler for updating cdu_type based on user selection."""
        try:
            selected_index = model.as_int
            self.current_cdu_type = self.cdu_options[selected_index]  # Update cdu_type with selected value
            self.update_calculations()  # Trigger recalculations if necessary
        except Exception as e:
            print(f"Error selecting CDU Type: {str(e)}")

    def update_climate_info(self, selected_city):
        try:
            selected_city = selected_city.strip()
            city_data = self.climate_data[self.climate_data['City'] == selected_city]

            if not city_data.empty:
                city_data = city_data.iloc[0]
                self.country_label.text = f"Country: {city_data['Country']}"
                self.state_label.text = f"State: {city_data['State'] if pd.notna(city_data['State']) else 'N/A'}"
                self.dry_bulb_label.text = f"Dry Bulb: {city_data['Dry Bulb']} °C"
                self.wet_bulb_label.text = f"Wet Bulb: {city_data['Wet Bulb']} °C"
                self.dew_point_label.text = f"Dew Point: {city_data['Dew Point']} °C"
                self.humidity_ratio_label.text = f"Humidity Ratio: {city_data['Humidity Ratio']}"
                self.dry_bulb = city_data['Dry Bulb']

            else:
                self._clear_labels()
                print("City data not found in CSV.")

        except Exception as e:
            print(f"Error updating climate info: {str(e)}")
            self._clear_labels()


    def update_liquid_cooling_options(self,fws_liquid_temp):
        try:
            selected_city = self.unique_cities[self.city_menu.model.get_item_value_model().as_int]
            city_data = self.climate_data[self.climate_data['City'] == selected_city]

            if not city_data.empty:
                dry_bulb = float(city_data['Dry Bulb'].iloc[0])
                wet_bulb = float(city_data['Wet Bulb'].iloc[0])

                if fws_liquid_temp - 5 - dry_bulb >= 0:
                    self.liquid_cooling_label1.text = "Liquid Cooling Option 1: Dry Cooler"
                else:
                    self.liquid_cooling_label1.text = "Liquid Cooling Option 1: Chiller"

                if fws_liquid_temp - 3 - wet_bulb >= 0:
                    self.liquid_cooling_label2.text = "Liquid Cooling Option 2: Closed Loop Cooling Tower"
                else:
                    self.liquid_cooling_label2.text = "Liquid Cooling Option 2: Chiller"
        except Exception as e:
            print(f"Error updating liquid cooling options: {str(e)}")
            self.liquid_cooling_label1.text = "Liquid Cooling Option 1: Not Set"
            self.liquid_cooling_label2.text = "Liquid Cooling Option 2: Not Set"

    def update_cooling_capacities(self):
        selected_pod_type = self.pod_options[self.pod_menu.model.get_item_value_model().as_int]
        total_air_cooling = self.calculate_total_air_cooling_capacity(selected_pod_type)
        liquid_cooling_capacity = self.calculate_total_liquid_cooling_capacity(selected_pod_type)

        # Display the cooling capacities in the UI
        self.total_air_cooling_label.text = f"Total Air Cooling Capacity: {total_air_cooling} kW"
        self.total_liquid_cooling_label.text = f"Total Liquid Cooling Capacity: {liquid_cooling_capacity} kW"


    def update_fws_design_temperature_liquid(self, tcs_liquid_value):

        # Calculate the maximum temperature based on TCS Liquid
        max_temp = max(5, tcs_liquid_value - 4)
        liquid_temp_range = list(range(5, max_temp + 1))
          # Debugging statement

        # Update ComboBox with new items
        self.fws_liquid_container.clear()
        with self.fws_liquid_container:
            ui.Label("FWS Design Temp (Liquid):", width=150, style=self.STYLES["label"])
            self.fws_liquid_menu = ui.ComboBox(0, *[str(temp) for temp in liquid_temp_range])  # Populate with calculated range
            ui.Label("°C", width=30)

        self.fws_liquid_menu.model.get_item_value_model().add_value_changed_fn(
                lambda model: self.update_liquid_cooling_options(int(self.fws_liquid_options[model.as_int]))
                        )


    def calculate_cdus(self, liquid_cooling_capacity, required_liquid_flow_rate_per_pod):
        # """
        # Calculate the number of CDUs based on total liquid cooling capacity and required liquid flow rate per pod.
        # Formula:
        # No. of CDUs = MAX(CEILING(liquid_cooling_capacity / XDU1350(nominal cooling capacity), 1),
        #                 CEILING(required_liquid_flow_rate_per_pod / Max Secondary Flow Rate CDU, 1)) + 1
        # """
        try:
            # Nominal cooling capacity for XDU1350
            xdu1350_capacity = self.NOMINAL_COOLING_CAPACITIES["XDU1350"]

            # Calculate number of CDUs based on cooling capacity and flow rate
            cdus_by_cooling_capacity = math.ceil(liquid_cooling_capacity / xdu1350_capacity)
            cdus_by_flow_rate = math.ceil(required_liquid_flow_rate_per_pod / self.MAX_SECONDARY_FLOW_RATE_CDU)

            # Final CDU count
            total_cdus = max(cdus_by_cooling_capacity, cdus_by_flow_rate) + 1
            return total_cdus
        except Exception as e:
            print(f"Error calculating CDUs: {e}")
            return None


    def update_fws_design_temperature_air(self,air_supply_temp):
        try:

            # Calculate the FWS Design Temperature Air range
            max_temp = max(5, air_supply_temp - 12)
            air_temp_range = list(range(5, max_temp + 1))

            # Clear the existing ComboBox and recreate it with the new range
            self.fws_air_container.clear()
            with self.fws_air_container:
                ui.Label("FWS Design Temp (Air):", width=150, style=self.STYLES["label"])
                # Populate ComboBox with the new air temperature range as strings
                self.fws_air_menu = ui.ComboBox(0, *[str(temp) for temp in air_temp_range])
                ui.Label("°C", width=30)

            # Attach an event listener to update `fws_design_temperature_air` when selection changes
            self.fws_air_menu.model.get_item_value_model().add_value_changed_fn(
                lambda model: self.calculate_chilled_water_temperature_rise(int(self.fws_air_options[model.as_int]))
                        )
            self.fws_air_menu.model.get_item_value_model().add_value_changed_fn(self.update_fws_design_temperature_air_value)
            self.fws_air_menu.model.get_item_value_model().add_value_changed_fn(self.calculate_chilled_water_temperature_rise)
            self.fws_air_menu.model.get_item_value_model().add_value_changed_fn(lambda model: self.update_calculations())

            # Initialize `fws_design_temperature_air` with the current ComboBox selection
            self.update_fws_design_temperature_air_value(self.fws_air_menu.model.get_item_value_model())
            # Ensuring update_calculations triggers when fws_air_menu changes



        except ValueError as e:
            print(f"ValueError in update_fws_design_temperature_air: {e}")
        except Exception as e:
            print(f"Unexpected error in update_fws_design_temperature_air: {e}")

    def update_fws_design_temperature_air_value(self, model):
        """Update `fws_design_temperature_air` based on ComboBox selection."""
        try:
            # Get the selected index and retrieve the actual value from the ComboBox options
            # Assuming fws_air_menu is defined as ui.ComboBox with a model
            children = self.fws_air_menu.model.get_item_children()
            selected_index = self.fws_air_menu.model.get_item_value_model(None).as_int

            # Get the selected item model and value as a string
            if 0 <= selected_index < len(children):
                selected_item_model = self.fws_air_menu.model.get_item_value_model(children[selected_index])
                self.fws_design_temperature_air = int(selected_item_model.get_value_as_string())

            else:
                print("Selected index is out of range")


        except Exception as e:
            print(f"Error updating FWS Design Temperature Air: {e}")



    def calculate_liquid_cooling_capacity(self, rack_type):
        # Calculate liquid cooling capacity as the difference between power per rack and air cooling per rack
        liquid_cooling_capacity = self.POWER_PER_RACK[rack_type] - self.AIR_COOLING_CAPACITY_PER_RACK[rack_type]
        return liquid_cooling_capacity

    def calculate_total_air_cooling_capacity(self, pod_type):
        rack_counts = self.POD_RACK_COUNTS.get(pod_type, {})
        total_air_cooling = sum(self.AIR_COOLING_CAPACITY_PER_RACK[rack] * count for rack, count in rack_counts.items())
        return total_air_cooling

    def calculate_total_liquid_cooling_capacity(self, pod_type):
        rack_counts = self.POD_RACK_COUNTS.get(pod_type, {})
        liquid_cooling_capacity = sum(self.calculate_liquid_cooling_capacity(rack) * count for rack, count in rack_counts.items())
        return liquid_cooling_capacity

    def calculate_power_per_pod(self, pod_type):
        # Retrieve rack breakdown for the selected pod type
        rack_counts = self.POD_RACK_COUNTS.get(pod_type, {})

        # Calculate the total power for this pod type
        total_power = sum(self.POWER_PER_RACK[rack] * count for rack, count in rack_counts.items())
        return total_power

    def calculate_rack_power_liquid_cooled(self, tcs_liquid_value):
    # """
    # Calculate the Rack Power for Liquid Cooling (kW) based on TCS Liquid Temperature.
    # Formula: Rack Power _Liquid Cooled (kW) = (44025 / (56.6 - TCS_liquid))^(0.576)
    # """
        try:
            rack_power_liquid_cooled = (44025 / (56.6 - tcs_liquid_value)) ** 0.576
            return rack_power_liquid_cooled
        except ZeroDivisionError:
            print("Error: TCS Liquid temperature is too close to 56.6, causing division by zero.")
            return None
        except Exception as e:
            print(f"Error calculating Rack Power _Liquid Cooled: {e}")
            return None

    def calculate_secondary_return_temp(self, rack_power_liquid_cooled, liquid_flow_rate_per_rack, tcs_liquid_value):
    # """
    #     Calculate the Secondary Return Temp (°C) LC.
    #     Formula: Secondary Return Temp (°C) LC = ((Rack Power _Liquid Cooled (kW) /
    #             (liquid_flow_rate_per_rack / 60000)) / Rho*C Secondary Flow) + TCS_liquid
    #     """
        try:
            if liquid_flow_rate_per_rack == 0:
                raise ValueError("Liquid flow rate per rack cannot be zero for this calculation.")

            temp_increase = (rack_power_liquid_cooled / (liquid_flow_rate_per_rack / 60000)) / self.RHO_C_SECONDARY_FLOW
            secondary_return_temp = temp_increase + tcs_liquid_value
            return secondary_return_temp
        except Exception as e:
            print(f"Error calculating Secondary Return Temp (°C) LC: {e}")
            return None

    def calculate_secondary_flowrate_per_cdu(self, required_liquid_flow_rate, total_cdus):
        return required_liquid_flow_rate / total_cdus

    def calculate_q_per_cdu(self, liquid_cooling_capacity, total_cdus):
        return liquid_cooling_capacity / total_cdus

    def calculate_primary_flow_rate_per_cdu(self, q_per_cdu):
        """
        Primary Flow Rate per CDU (LPM) = (Q/CDU / Primary Delta Temp) / (4170 * 60000)
        """
        return ((q_per_cdu / self.PRIMARY_DELTA_TEMP) / 4170) * 60000

    def calculate_q_max_cdu(self, required_liquid_flow_rate, total_cdus, secondary_return_temp, primary_supply_temp,liquid_cooling_capacity):
        """
        Q_max_CDU = Rho*C Secondary Flow * MIN(Secondary Flow Rate per CDU, Primary Flow Rate per CDU) / 60000 * (Secondary Return Temp - Primary Supply Temp)
        """
        q_per_cdu = self.calculate_q_per_cdu(liquid_cooling_capacity, total_cdus)
        secondary_flow_rate_per_cdu = self.calculate_secondary_flowrate_per_cdu(required_liquid_flow_rate, total_cdus)
        primary_flow_rate_per_cdu = self.calculate_primary_flow_rate_per_cdu(q_per_cdu)

        min_flow_rate = min(secondary_flow_rate_per_cdu, primary_flow_rate_per_cdu)
        delta_temp = secondary_return_temp - primary_supply_temp

        return (self.RHO_C_SECONDARY_FLOW * min_flow_rate / 60000) * delta_temp

    def calculate_primary_flow_rate_per_pod(self, primary_flow_rate_per_cdu, total_cdus):
        return primary_flow_rate_per_cdu * total_cdus

    def calculate_total_power(self):
        try:
            # Get the selected pod type and the number of pods
            selected_pod_type = self.pod_options[self.pod_menu.model.get_item_value_model().as_int]
            num_pods = int(self.num_pods_field.model.get_value_as_string())

            # Calculate the power per pod
            power_per_pod = self.calculate_power_per_pod(selected_pod_type)

            # Calculate total power based on the number of pods
            total_power = power_per_pod * num_pods

            # Display the total power in the UI
            self.total_power_label.text = f"Total Power: {total_power} kW"

        except ValueError:
            # Handle cases where the input is not a valid integer
            self.total_power_label.text = "Enter a valid number of pods."

        # Function to calculate required air flow rate per kW (CFM)
    def calculate_air_flow_rate_per_kw(self, air_supply_temp):
        # Formula: CFM = 0.0054667 * (T^3) - 0.34 * (T^2) + 10.263333 * T - 13
        cfm_per_kw = (
            0.0054667 * (air_supply_temp ** 3) -
            0.34 * (air_supply_temp ** 2) +
            10.263333 * air_supply_temp -
            13
        )

        return cfm_per_kw

    # Function to calculate required air flow rate per rack (CFM)
    def calculate_air_flow_rate_per_rack(self, pod_type, air_supply_temp):
        # Retrieve total air cooling capacity per rack for the selected pod type
        air_cooling_capacity_per_rack = self.AIR_COOLING_CAPACITY_PER_RACK["GB200_NVL72"]

        # Calculate air flow rate per kW
        air_flow_rate_per_kw = self.calculate_air_flow_rate_per_kw(air_supply_temp)

        # Calculate air flow rate per rack
        air_flow_rate_per_rack = air_flow_rate_per_kw * (air_cooling_capacity_per_rack / 1)  # in kW/rack
        return air_flow_rate_per_rack

    # Function to calculate required liquid flow rate per rack
    def calculate_liquid_flow_rate_per_rack(self, tcs_liquid_temp):
        # Formula: Liquid Flow Rate = (44025 / (56.6 - TCS Liquid))^(0.576)
        liquid_flow_rate_per_rack = ( -0.0007656 * (tcs_liquid_temp ** 4) +
            0.11484 * (tcs_liquid_temp ** 3) -
            6.18222 * (tcs_liquid_temp ** 2) +
            145.2726 * tcs_liquid_temp -
            1205.82)
        return liquid_flow_rate_per_rack

    def update_flow_rates(self):
        """Main method to update flow rates in the UI."""
        try:

                    # Get the selected pod type
            selected_pod_type = self.pod_options[self.pod_menu.model.get_item_value_model().as_int]

            # Calculate the required liquid cooling capacity per pod based on the selected pod type
            liquid_cooling_capacity = self.calculate_total_liquid_cooling_capacity(selected_pod_type)

            # Calculate liquid flow rate per pod and update the UI label
            required_liquid_flow_rate_per_pod = self.calculate_liquid_flow_rate_per_pod()
            self.required_liquid_flow_rate_label.text = f"Required Liquid Flow Rate per Pod (LPM): {required_liquid_flow_rate_per_pod:.2f}"

            # Calculate total CDUs and update the UI label
            total_cdus = self.calculate_cdus(liquid_cooling_capacity, required_liquid_flow_rate_per_pod)
            self.total_cdus_label.text = f"Number of CDUs: {total_cdus}" if total_cdus else "Calculation error"

            # Calculate primary and secondary flow rates per CDU and per pod
            self.calculate_primary_and_secondary_flowrates(total_cdus, required_liquid_flow_rate_per_pod)
            self.update_pod_flowrate_and_curve(selected_pod_type, total_cdus, required_liquid_flow_rate_per_pod)


        except Exception as e:
            print(f"Unexpected error in update_flow_rates: {e}")

    ### Sub-Methods for Calculations

    def update_calculations(self):
        """Main method to perform all calculations and update UI."""
        try:

            current_cdu_type = self.cdu_options[self.cdu_menu.model.get_item_value_model().as_int]
            num_pods = int(self.num_pods_field.model.get_value_as_string())
            air_supply_temperature = self.get_selected_air_supply_temperature() # Fetch the selected air supply temperature

            selected_pod_type = self.pod_options[self.pod_menu.model.get_item_value_model().as_int]
            air_cooling_capacity_per_pod = self.calculate_total_air_cooling_capacity(selected_pod_type)
            required_air_flow_rate_capacity_per_pod = self.calculate_airflow_rate_per_pod(air_supply_temperature)

            fws_air_temperature = self.get_selected_fws_design_air_temperature()

            # Calculate air temperature rise in rack
            air_temperature_rise_in_rack = self.calculate_air_temperature_rise_in_rack(air_cooling_capacity_per_pod, required_air_flow_rate_capacity_per_pod)
            self.air_temperature_rise_label.text = f"Air Temperature Rise in Rack: {air_temperature_rise_in_rack:.2f} °C"

            # Calculate air return temperature
            air_return_temperature = self.calculate_air_return_temperature(air_supply_temperature, air_temperature_rise_in_rack)
            self.air_return_temperature_label.text = f"Air Return Temperature: {air_return_temperature:.2f} °C"

            self.required_airflow_rate_label.text = f"Required Air Flow Rate per Pod (CFM): {required_air_flow_rate_capacity_per_pod:.2f}" if required_air_flow_rate_capacity_per_pod else "Calculation error"

            # Calculate number of CRAHs
            no_of_crahs = self.calculate_no_of_crahs(air_cooling_capacity_per_pod)

                    # Update CRAH count label for Vertiv PW170
            self.crah_label_vertiv_pw170.text = f"Number of CRAHs for Vertiv PW170: {no_of_crahs}"

            # Calculate Q per CRAH based on CDU type
            total_power_per_pod = self.calculate_power_per_pod(selected_pod_type)  # Replace with your actual calculation
            q_per_crah = self.calculate_q_per_crah(current_cdu_type, air_cooling_capacity_per_pod, total_power_per_pod, no_of_crahs)
            self.q_per_crah_label.text = f"Q per CRAH: {q_per_crah:.2f} kW"

            chilled_water_temperature_rise = self.calculate_chilled_water_temperature_rise(fws_air_temperature)

            # Calculate chilled water flow rate per CRAH
            chilled_water_flow_rate_crah = self.calculate_chilled_water_flow_rate_per_crah(q_per_crah, chilled_water_temperature_rise)
            self.chilled_water_flow_rate_crah_label.text = f"Chilled Water Flow Rate per CRAH (LPM): {chilled_water_flow_rate_crah:.2f}"

            # Calculate chilled water flow rate per POD
            chilled_water_flow_rate_pod = self.calculate_chilled_water_flow_rate_per_pod(chilled_water_flow_rate_crah, no_of_crahs)
            self.chilled_water_flow_rate_pod_label.text = f"Chilled Water Flow Rate per POD (LPM): {chilled_water_flow_rate_pod:.2f}"

            q_ac_per_pod = self.calculate_q_ac_per_pod(current_cdu_type, air_cooling_capacity_per_pod, total_power_per_pod, num_pods)
            self.q_ac_per_pod_label.text = f"Q AC per POD (kW): {q_ac_per_pod:.2f}"

            self.calculate_crah_rpm_and_power(required_air_flow_rate_capacity_per_pod,no_of_crahs)
        except Exception as e:
            print(f"Error in update_calculations: {e}")


    def calculate_air_return_temperature(self, air_supply_temperature, air_temperature_rise_in_rack):
        """Calculate the air return temperature."""
        return air_supply_temperature + air_temperature_rise_in_rack

    def calculate_air_temperature_rise_in_rack(self, air_cooling_capacity_per_pod, required_air_flow_rate_capacity_per_pod):
        """Calculate the air temperature rise in rack."""
        return air_cooling_capacity_per_pod / 1.08 / (required_air_flow_rate_capacity_per_pod * 0.00047194745)

    def calculate_airflow_rate_per_pod(self, air_supply_temp):
        """Calculate and return required airflow rate per pod (CFM) based on the selected air supply temperature."""
        try:
            # Calculate air flow rate for the primary rack (GB200_NVL72) based on air supply temperature
            air_flow_rate_per_rack_gb200 = self.calculate_air_flow_rate_per_rack("GB200_NVL72", air_supply_temp)

            # Retrieve rack counts for the selected pod type
            selected_pod_type, rack_counts = self.get_selected_pod_info()
            print("Air_flow_rate_per_rack",air_flow_rate_per_rack_gb200)
            print("No of racks", rack_counts.get("GB200_NVL72", 0))
            no_of_racks_gb200 = rack_counts.get("GB200_NVL72", 0)
            no_of_racks_management = rack_counts.get("Management",0)
            no_of_racks_networking = rack_counts.get("Networking", 0)
            GB200_flow_rate = air_flow_rate_per_rack_gb200 * no_of_racks_gb200
            Management_rack_flow_rate = self.AIR_FLOW_RATE_MANAGEMENT_RACK * no_of_racks_management
            Networking_rack_flow_rate = self.AIR_FLOW_RATE_NETWORK_RACK * no_of_racks_networking

            # Calculate the total required airflow rate per pod
            required_airflow_rate_per_pod = (
                GB200_flow_rate +
                Management_rack_flow_rate +
                Networking_rack_flow_rate
            )

            return (required_airflow_rate_per_pod * 1.05)
        except Exception as e:
            print(f"Error calculating airflow rate per pod: {str(e)}")
            return None


    def calculate_liquid_flow_rate_per_pod(self):
        """Calculate and return required liquid flow rate per pod (LPM)."""
        tcs_liquid_temp = self.get_selected_tcs_liquid_temperature()
        liquid_flow_rate_per_rack_gb200 = self.calculate_liquid_flow_rate_per_rack(tcs_liquid_temp)
        selected_pod_type, rack_counts = self.get_selected_pod_info()

        required_liquid_flow_rate_per_pod = liquid_flow_rate_per_rack_gb200 * rack_counts.get("GB200_NVL72", 0)
        return required_liquid_flow_rate_per_pod


    def calculate_primary_and_secondary_flowrates(self, total_cdus, required_liquid_flow_rate_per_pod):
        """Calculate and update primary and secondary flow rates per CDU and per Pod in the UI."""
        if total_cdus is None:
            print("Error: Total CDUs not calculated.")
            return

        # Secondary flow rate per CDU
        secondary_flowrate_per_cdu = self.calculate_secondary_flowrate_per_cdu(required_liquid_flow_rate_per_pod, total_cdus)
        self.secondary_flow_rate_per_cdu_label.text = f"Secondary Flowrate per CDU (LPM): {secondary_flowrate_per_cdu:.2f}"

        # Primary flow rate per CDU and per Pod
        q_per_cdu = self.calculate_q_per_cdu(self.calculate_total_liquid_cooling_capacity(self.get_selected_pod_info()[0]), total_cdus)

        primary_flow_rate_per_cdu = self.calculate_primary_flow_rate_per_cdu(q_per_cdu)

        self.primary_flow_rate_per_cdu_label.text = f"Primary Flow Rate per CDU (LPM): {primary_flow_rate_per_cdu:.2f}"

        primary_flow_rate_per_pod = self.calculate_primary_flow_rate_per_pod(primary_flow_rate_per_cdu, total_cdus)
        self.primary_flow_rate_per_pod_label.text = f"Primary Flow Rate per POD (LPM): {primary_flow_rate_per_pod:.2f}"

    ### Helper Methods

    def get_selected_air_supply_temperature(self):
        """Retrieve selected air supply temperature."""
        air_supply_index = self.air_supply_menu.model.get_item_value_model().as_int
        return int(self.air_supply_options[air_supply_index])

    def get_selected_tcs_liquid_temperature(self):
        """Retrieve selected TCS liquid temperature."""
        tcs_liquid_index = self.tcs_liquid_menu.model.get_item_value_model().as_int
        return int(self.tcs_liquid_options[tcs_liquid_index])

    def get_selected_fws_design_air_temperature(self):
        fws_air_index = self.fws_air_menu.model.get_item_value_model().as_int
        return int(self.fws_air_options[fws_air_index])

    def get_selected_fws_design_liquid_temperature(self):
        fws_liquid_index = self.fws_air_menu.model.get_item_value_model().as_int
        return int(self.fws_air_options[fws_liquid_index])
    def get_selected_pod_info(self):
        """Retrieve selected pod type and rack counts for the selected pod configuration."""
        selected_pod_type = self.pod_options[self.pod_menu.model.get_item_value_model().as_int]
        rack_counts = self.POD_RACK_COUNTS.get(selected_pod_type, {})
        return selected_pod_type, rack_counts

    def update_pod_flowrate_and_curve(self, selected_pod_type, total_cdus, required_liquid_flow_rate_per_pod):
        """Calculate POD flowrate per CDU using existing total CDUs and log QSC coefficients."""
        try:
            # Calculate POD flow rate per CDU
            POD_flowrate_CDU = required_liquid_flow_rate_per_pod / total_cdus

            # Update the UI label with calculated POD Flow Rate per CDU
            self.pod_flowrate_cdu_label.text = f"POD Flow Rate per CDU: {POD_flowrate_CDU:.2f} LPM"

            # Optionally: Log QSC data for internal debugging
            if selected_pod_type in self.QSC_COEFFICIENTS and total_cdus in self.QSC_COEFFICIENTS[selected_pod_type]:
                qsc_coefficients = self.QSC_COEFFICIENTS[selected_pod_type][total_cdus]
                qsc_a, qsc_b, qsc_c = qsc_coefficients["a"], qsc_coefficients["b"], qsc_coefficients["c"]

                                # Calculate QES coefficients
                qes_a = self.XDU_PQC["a"] - qsc_a
                qes_b = self.XDU_PQC["b"] - qsc_b
                qes_c = self.XDU_PQC["c"] - qsc_c

                                # Calculate roots of the quadratic equation
                root1, root2 = self.calculate_roots(qes_a, qes_b, qes_c)
                                # Calculate flowrate1 as the maximum of root1 and root2
                flowrate1 = max(root1, root2)

                                # Calculate dp1 and dp2
                dp1 = self.calculate_dp(qsc_coefficients, flowrate1)
                dp2 = self.calculate_dp(qsc_coefficients, POD_flowrate_CDU)

                                # Calculate rpm2 and HP2
                rpm2 = math.sqrt(dp2 / dp1) * (self.rpm1 ** 2)
                hp2 = ((rpm2 / self.rpm1) ** 3) * self.HP1
                hp_per_pod = hp2 * total_cdus

                                # Display HP2 and HP per pod in the UI
                self.cdu_hp2_label.text = f"HP2 (kW): {hp2:.2f}"
                self.cdu_hp_per_pod_label.text = f"HP per Pod: {hp_per_pod:.2f}"

        except Exception as e:
            print(f"Error in update_pod_flowrate_and_curve: {e}")

    def calculate_roots(self, a, b, c):
        """Calculate and return the roots of the quadratic equation."""
        try:
            # Calculate the discriminant
            discriminant = b**2 - 4 * a * c

            # Check if discriminant is non-negative for real roots
            if discriminant < 0:
                print("No real roots exist.")
                return None, None

            # Calculate the two roots using the quadratic formula
            sqrt_discriminant = math.sqrt(discriminant)
            root1 = (-b + sqrt_discriminant) / (2 * a)
            root2 = (-b - sqrt_discriminant) / (2 * a)

            return root1, root2
        except Exception as e:
            print(f"Error calculating roots: {e}")
            return None, None

    def calculate_dp(self, qsc_coefficients, flowrate):
        """Calculate the differential pressure (dp) based on flowrate."""
        a = qsc_coefficients["a"]
        b = qsc_coefficients["b"]
        c = qsc_coefficients["c"]
        dp = a * (flowrate ** 2) + b * flowrate + c
        return dp

    def calculate_no_of_crahs(self, air_cooling_capacity_per_pod):
        """Calculate number of CRAHs based on air cooling capacity and CRAH model data."""
        crah_model_capacity = self.vendor_data[2]["Net Total Capacity (kW)"]  # Replace with logic to select specific model if needed
        return math.ceil(air_cooling_capacity_per_pod / crah_model_capacity)


    def calculate_chilled_water_temperature_rise(self, fws_design_temperature_air):
        """Calculate chilled water temperature rise based on conditions."""
        try:
            model_filter = "Vertiv 1MW"
            ta = math.ceil(self.dry_bulb)

            # Filter for rows where TWOUT matches fws_design_temperature and TA matches the ceiling of dry_bulb
            target_row = self.chillers_data[
                (self.chillers_data['Model'] == model_filter) &
                (self.chillers_data['TWOUT'] == fws_design_temperature_air) &
                (self.chillers_data['TA '] == ta)
            ]

            if not target_row.empty:
                # Retrieve the 'evaporator' value for chilled water temperature rise
                chilled_water_temp_rise = target_row.iloc[0]['Evaporator']
                return chilled_water_temp_rise
            else:
                print("No matching row found in chillers.csv for the specified conditions.")
                return None

        except Exception as e:
            print(f"Error calculating chilled water temperature rise: {e}")
            return None

    def calculate_q_per_crah(self, cdu_type, air_cooling_capacity_per_pod, total_power_per_pod, no_of_crahs):
        """Calculate Q per CRAH based on CDU type."""

        if cdu_type == "Liquid to Liquid":
            return air_cooling_capacity_per_pod / no_of_crahs
        elif cdu_type == "Liquid to Air":
            return total_power_per_pod / no_of_crahs
        return 0  # Return a default value if CDU type is unrecognized

    def calculate_chilled_water_flow_rate_per_crah(self, q_per_crah, chilled_water_temperature_rise):
        """Calculate the chilled water flow rate per CRAH."""
        return (q_per_crah / (chilled_water_temperature_rise * self.water_rho_cp)) * 60000

    def calculate_chilled_water_flow_rate_per_pod(self, chilled_water_flow_rate_crah, no_of_crahs):
        """Calculate the chilled water flow rate per POD."""
        return chilled_water_flow_rate_crah * no_of_crahs

    def calculate_q_ac_per_pod(self, cdu_type, air_cooling_capacity_per_pod, total_power_per_pod, no_of_pods):

        """Calculate Q AC per POD based on CDU type."""
        if cdu_type == "Liquid to Liquid":
            return air_cooling_capacity_per_pod
        elif cdu_type == "Liquid to Air":
            return total_power_per_pod
        return 0  # Return a default value if CDU type is unrecognized

    def calculate_crah_rpm_and_power(self,required_airflow_rate_capacity_per_pod, no_of_crahs):
        try:
            # Calculate CFM2
            CFM2 = required_airflow_rate_capacity_per_pod / no_of_crahs
            print(f"Calculated CFM2: {CFM2} CFM")

            # Calculate RPM2% using the defined RPM1_PERCENT constant
            RPM2_percent = (CFM2 / self.CFM1) * self.RPM1_PERCENT
            print(f"Calculated RPM2%: {RPM2_percent}")
            HP1_per_CRAH = self.HP1_PER_CRAH

            # Calculate HP2_per_crah using the constants
            HP2_per_crah = ((RPM2_percent / self.RPM1_PERCENT) ** 3) * self.HP1_PER_CRAH
            print(f"Calculated HP2_per_crah: {HP2_per_crah} kW")

            # Display the results in the UI if labels are set up for them
            self.crah_hp2_label.text = f"HP2 per CRAH: {HP2_per_crah:.2f} kW"
            self.crah_hp1_label.text = f"HP1 per CRAH: {HP1_per_CRAH:.2f}%"

        except Exception as e:

            print(f"Error calculating CRAH RPM and power: {e}")

    def _clear_labels(self):
        self.country_label.text = "Country: N/A"
        self.state_label.text = "State: N/A"
        self.dry_bulb_label.text = "Dry Bulb: N/A"
        self.wet_bulb_label.text = "Wet Bulb: N/A"
        self.dew_point_label.text = "Dew Point: N/A"
        self.humidity_ratio_label.text = "Humidity Ratio: N/A"

    def on_shutdown(self):
        print("My Extension is shutting down")

        # air_flow_rate_per_rack(Management rack) = 3900
        # air_flow_rate_per_rack(Network rack) = 3900
        # required airflow rate/pod = [(air_flow_rate_per_rack(GB200_NVL 72) *no.of racks(GB200_NVL 72)) + air_flow_rate_per_rack(Management rack) * no.of racks(Management Rack) + air_flow_rate_per_rack(Network rack) * no.of racks(Network Rack)

        # RPM1% = 1
        # RPM2% = (CFM2/CFM1) * RPM1

        # CFM2= Required_airflow_rate_per_pod/ no of crahs per pod
        # CFM1 = PW170 CFM value = 29081

        # HP1_per_crah = PW170 Total power = 13.5 kW
        # HP2_per_crah = ((RPM2%/RPM!%)^3)* HP1_per_crah