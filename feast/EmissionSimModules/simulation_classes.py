"""
    simulation_classes stores the classes used to represent time, results and financial settings in simulations.
"""
import os
import pickle
from ..DetectionModules.ldar_program import LDARProgram
import json


class Time:
    """
    Instances of the time class store all time related information during a simulation
    """
    def __init__(self, delta_t=1, end_time=365, current_time=0):
        """
        :param delta_t: length of one timestep (days)
        :param end_time: length of the simulation (days)
        :param current_time: current time in a simulation (days)
        """
        self.n_timesteps = int(end_time / delta_t)
        self.end_time = end_time
        self.delta_t = delta_t
        self.current_time = current_time
        self.time_index = 0


class Scenario:
    """
    A class to store all data specifying a scenario and the methods to run and save a realization
    """
    def __init__(self, time, gas_field, ldar_program_dict):
        """
        :param time: Time object
        :param gas_field: GasField object
        :param ldar_program_dict: dict of detection methods and associated data
        """
        self.time = time
        self.gas_field = gas_field
        self.ldar_program_dict = ldar_program_dict

    def run(self, dir_out="Results", display_status=True, save_method='json'):
        """
        run generates a single realization of a scenario.

        :param dir_out: path to a directory in which to save results (string)
        :param display_status: if True, display a status update whenever 10% of the time steps are completed
        :return: None
        """
        # -------------- Define settings --------------
        # time defines parameters related to time in the model. Time units are days.
        if 'Null' not in self.ldar_program_dict:
            self.ldar_program_dict['Null'] = LDARProgram(self.time, self.gas_field, tech_dict={})
        # -------------- Run the simulation --------------
        # check_timestep(gas_field, time)
        for self.time.time_index in range(0, self.time.n_timesteps):
            if display_status and self.time.current_time % (self.time.end_time / 10) < self.time.delta_t:
                print("The evaluation is {:0.0f}% complete".format(100 * self.time.time_index / self.time.n_timesteps))
            # Loop through each LDAR program:
            for lp in self.ldar_program_dict.values():
                lp.action(self.time, self.gas_field)
                t0 = self.time.current_time
                lp.emissions_timeseries.append(lp.emissions.em_rate_in_range(t0, t0 + self.time.delta_t))
                lp.vents_timeseries.append(lp.emissions.em_rate_in_range(t0, t0 + self.time.delta_t, reparable=False))
            self.time.current_time += self.time.delta_t

        # -------------- Save results --------------
        self.save(dir_out, method=save_method)

    def save(self, dir_out, method='json'):
        """
        Save results to a file

        :param dir_out: Name of directory in which to save output file.
        :param method: Specifies how results should be saved
        """

        if not os.path.exists(dir_out):
            os.makedirs(dir_out)
        n_realization = len([real for real in os.listdir(dir_out) if '.json' in real])
        file_out = dir_out + '/realization' + str(n_realization)
        res_dict = {}
        for prog_name, prog in self.ldar_program_dict.items():
            res_dict[prog_name] = {
                'emission timeseries': prog.emissions_timeseries,
                'vent timeseries': prog.vents_timeseries,
            }
            for tech_name, tech in prog.tech_dict.items():
                res_dict[prog_name][tech_name] = {}
                res_dict[prog_name][tech_name]['deployment costs'] = tech.deployment_cost.__dict__
                res_dict[prog_name][tech_name]['deployment count'] = tech.deployment_count.__dict__
                res_dict[prog_name][tech_name]['op env site fails'] = tech.op_env_site_fails.__dict__
                res_dict[prog_name][tech_name]['op env field fails'] = tech.op_env_field_fails.__dict__
            for rep_name, rep in prog.repair.items():
                res_dict[prog_name][rep_name] = {}
                res_dict[prog_name][rep_name]['repair cost'] = rep.repair_cost.__dict__
                res_dict[prog_name][rep_name]['repair count'] = rep.repair_count.__dict__
        with open(file_out + '.json', 'w') as f:
            json.dump(res_dict, f)
        if method not in ['json', 'pickle']:
            raise ValueError("The specified save method does not exist. Results were saved to a JSON file.")
        if method == 'pickle':
            pickle.dump(self, open(file_out + '.p', 'wb'))

    def check_timestep(self):
        """
        Prints a warning if time.delta_t is greater than the duration of some permitted emissions

        :param gas_field: a GasField object
        :param time: a Time object
        :return: None
        """
        for sitedict in self.gas_field.sites.values():
            site = sitedict['parameters']
            for comp_temp in site.comp_dict.values():
                comp = comp_temp['parameters']
                if 0 < comp.episodic_emission_duration < self.time.delta_t:
                    print(
                        "Warning: Episodic emission duration in site '{}', component '{}' is less than the simulation "
                        "time step.\n"
                        "Episodic emissions will be treated as though they have a duration of one time step.".format(
                            site.name, comp.name))
