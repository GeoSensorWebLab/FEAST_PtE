import numpy as np
import copy
import feast
import os
import pickle
import time as ti
from feast.EmissionSimModules import simulation_classes as sc
import feast.EmissionSimModules.emission_class_functions as ecf
from feast import DetectionModules as Dm
from Tests.test_helper import basic_gas_field
from Tests.test_helper import ex_prob_detect_arrays


def test_repair():
    n_em = 10
    flux, capacity, reparable, repair_cost = np.zeros(n_em), 10, np.zeros(n_em, dtype=bool), np.ones(n_em)
    site_index, comp_index = np.zeros(n_em), np.zeros(n_em)
    flux[5:] = 1
    reparable[3: 8] = True
    endtime = np.linspace(0, 9, n_em)
    emission = ecf.Emission(flux, capacity, reparable, site_index, comp_index, repair_cost=repair_cost, endtime=endtime)
    time = sc.Time()
    time.time_index = 3
    time.current_time = 4.5
    detected = np.array([3, 4, 5, 6, 7, 8, 9], dtype=int)
    repair_proc = Dm.repair.Repair(repair_delay=1)
    repair_proc.action(emit_inds=detected)
    repair_proc.repair(time, emission)
    expected = np.array([0., 1., 2., 3., 4., 5., 5.5, 5.5, 8., 9.])
    for ind in range(len(emission.endtime)):
        if emission.endtime[ind] != expected[ind]:
            raise ValueError("DetectionModules.repair.Repair is not adjusting "
                             "emission endtimes correctly at index {:0.0f}".format(ind))


def test_check_time():
    time = sc.Time(delta_t=1, end_time=10, current_time=0)
    rep = Dm.repair.Repair(repair_delay=0)
    tech = Dm.comp_survey.CompSurvey(
        time,
        survey_interval=50,
        dispatch_object=rep
    )
    if not tech.check_time(time):
        raise ValueError("Check time returning False when it should be true at time 0")
    time = sc.Time(delta_t=0.1, end_time=10, current_time=0)
    tech = Dm.comp_survey.CompSurvey(
        time,
        survey_interval=50,
        dispatch_object=rep
    )
    if tech.check_time(time):
        raise ValueError("check_time returning True when it should return False at time 0")


def test_comp_survey():
    gas_field = basic_gas_field()
    time = sc.Time(delta_t=1, end_time=10, current_time=0)
    find_cost = np.zeros(time.n_timesteps)
    rep = Dm.repair.Repair(repair_delay=0)
    points = np.logspace(-3, 1, 100)
    probs = 0.5 + 0.5 * np.array([np.math.erf((np.log(f) - np.log(0.02)) / (0.8 * np.sqrt(2))) for f
                                  in points])
    tech = Dm.comp_survey.CompSurvey(
        time,
        survey_interval=50,
        survey_speed=150,
        ophrs={'begin': 8, 'end': 17},
        labor=100,
        dispatch_object=rep,
        detection_variables={'flux': 'mean'},
        detection_probability_points=points,
        detection_probabilities=probs
    )
    emissions = gas_field.initial_emissions
    tech.action(list(np.linspace(0, gas_field.n_sites - 1, gas_field.n_sites, dtype=int)))
    tech.detect(time, gas_field, emissions, find_cost)
    if np.max(emissions.site_index[rep.to_repair]) != 13:
        raise ValueError("tech.detect repairing emissions at incorrect sites")
    expected_detected_inds = [54, 55, 75, 66, 87, 62, 58, 84, 5, 25, 43, 71, 13, 79, 97]
    for ind in range(len(rep.to_repair)):
        if expected_detected_inds[ind] != rep.to_repair[ind]:
            raise ValueError("tech.detect not detecting the correct emissions")
    if len(expected_detected_inds) != len(rep.to_repair):
        raise ValueError("tech.detect not detecting the correct emissoins")
    rep.repair(time, emissions)
    if np.max(emissions.endtime[np.array(expected_detected_inds)]) != 0:
        raise ValueError("rep.repair not adjusting the end times correctly")


def test_comp_survey_emitters_surveyed():
    gas_field = basic_gas_field()
    gas_field.met_data_path = 'TMY-DataExample.csv'
    time = sc.Time(delta_t=1, end_time=10, current_time=0)
    gas_field.met_data_maker()
    find_cost = np.zeros(time.n_timesteps)
    rep = Dm.repair.Repair(repair_delay=0)
    wind_dirs_mins = np.zeros(gas_field.n_sites)
    wind_dirs_maxs = np.ones(gas_field.n_sites) * 90
    points = np.logspace(-3, 1, 100)
    probs = 0.5 + 0.5 * np.array([np.math.erf((np.log(f) - np.log(0.02)) / (0.8 * np.sqrt(2))) for f
                                  in points])
    tech = Dm.comp_survey.CompSurvey(
        time,
        survey_interval=50,
        survey_speed=150,
        ophrs={'begin': 8, 'end': 17},
        labor=100,
        dispatch_object=rep,
        op_envelope={
            'wind speed': {'class': 1, 'min': 1, 'max': 10},
            'wind direction': {'class': 2, 'min': wind_dirs_mins, 'max': wind_dirs_maxs}
        },
        detection_variables={'flux': 'mean'},
        detection_probability_points=points,
        detection_probabilities=probs
    )
    tech.action(list(np.linspace(0, gas_field.n_sites - 1, gas_field.n_sites, dtype=int)))
    emissions = gas_field.initial_emissions
    emitter_inds = tech.emitters_surveyed(time, gas_field, emissions, find_cost)
    if emitter_inds:
        # emitter_inds is expected to be []
        raise ValueError("CompSurvey.emitters_surveyed is not returning expected emitter indexes")
    wind_dirs_maxs[11] = 200
    emitter_inds = tech.emitters_surveyed(time, gas_field, emissions, find_cost)
    if emitter_inds != [71]:
        # The wind direction op envelope was updated to pass at site 11 only. Site 11 has one emission at index 71.
        raise ValueError("CompSurvey.emitters_surveyed is not returning expected indexes")


def test_site_survey():
    gas_field = basic_gas_field()
    time = sc.Time(delta_t=1, end_time=10, current_time=0)
    find_cost = np.zeros(time.n_timesteps)
    # Test __init__
    points = np.logspace(-3, 1, 100)
    probs = 0.5 + 0.5 * np.array([np.math.erf((np.log(f) - np.log(0.474)) / (1.36 * np.sqrt(2))) for f
                                  in points])
    tech = Dm.site_survey.SiteSurvey(
        time,
        survey_interval=50,
        sites_per_day=100,
        ophrs={'begin': 8, 'end': 17},
        site_cost=100,
        dispatch_object=Dm.comp_survey.CompSurvey(time),
        detection_variables={'flux': 'mean'},
        detection_probability_points=points,
        detection_probabilities=probs
    )
    emissions = gas_field.initial_emissions
    np.random.seed(0)
    # test detect_prob_curve
    detect = tech.detect_prob_curve(time, gas_field, [0, 1, 2], emissions)
    if detect != np.array([0]):
        raise ValueError("site_detect.detect_prob_curve not returning expected sites.")
    # test sites_surveyed with empty queue
    sites_surveyed = tech.sites_surveyed(gas_field, time, find_cost)
    if sites_surveyed:
        raise ValueError("sites_surveyed returning sites when it should not")
    if find_cost[0] > 0:
        raise ValueError("sites_surveyed updating find_cost when it should not")
    # test detect
    np.random.seed(0)
    tech.site_queue = [0, 1, 2]
    tech.detect(time, gas_field, emissions, np.zeros(time.n_timesteps))
    if tech.dispatch_object.site_queue != [0]:
        raise ValueError("site_detect.detect not updating dispatch object sites to survey correctly")
    # test action and sites_surveyed with
    tech.action(list(np.linspace(0, gas_field.n_sites - 1, gas_field.n_sites, dtype=int)))
    if tech.site_queue != list(np.linspace(0, gas_field.n_sites - 1, gas_field.n_sites, dtype=int)):
        raise ValueError("action is not updating site_queue as expected")
    # test sites_surveyed with full queue
    sites_surveyed = tech.sites_surveyed(gas_field, time, find_cost)
    if (sites_surveyed != np.linspace(0, 99, 100, dtype=int)).any():
        raise ValueError("sites_surveyed not identifying the correct sites")
    if find_cost[0] != 10000:
        raise ValueError("sites_surveyed not updating find_cost as expected.")


def test_sitedetect_sites_surveyed():
    gas_field = basic_gas_field()
    gas_field.met_data_path = 'TMY-DataExample.csv'
    time = sc.Time(delta_t=1, end_time=10, current_time=0)
    gas_field.met_data_maker()
    find_cost = np.zeros(time.n_timesteps)
    wind_dirs_mins = np.zeros(gas_field.n_sites)
    wind_dirs_maxs = np.ones(gas_field.n_sites) * 90
    wind_dirs_maxs[50] = 270
    tech = Dm.site_survey.SiteSurvey(
        time,
        survey_interval=50,
        sites_per_day=100,
        ophrs={'begin': 8, 'end': 17},
        site_cost=100,
        dispatch_object=Dm.comp_survey.CompSurvey(time),
        op_envelope={
            'wind speed': {'class': 1, 'min': 1, 'max': 10},
            'wind direction': {'class': 2, 'min': wind_dirs_mins, 'max': wind_dirs_maxs}
        }
    )
    tech.site_queue = list(np.linspace(0, gas_field.n_sites - 1, gas_field.n_sites, dtype=int))
    np.random.seed(0)
    sites_surveyed = tech.sites_surveyed(gas_field, time, find_cost)
    if sites_surveyed != [50]:
        raise ValueError("sites_surveyed is not returning sites correctly")
    if find_cost[0] != 100:
        raise ValueError("sites_surveyed incorrectly updating find_cost")


def test_ldar_program():
    gas_field = basic_gas_field()
    time = sc.Time(delta_t=1, end_time=10, current_time=0)
    rep = Dm.repair.Repair(repair_delay=0)
    points = np.logspace(-3, 1, 100)
    probs = 0.5 + 0.5 * np.array([np.math.erf((np.log(f) - np.log(0.02)) / (0.8 * np.sqrt(2))) for f
                                  in points])
    probs[0] = 0
    ogi = Dm.comp_survey.CompSurvey(
        time,
        survey_interval=50,
        survey_speed=150,
        ophrs={'begin': 8, 'end': 17},
        labor=100,
        dispatch_object=rep,
        detection_variables={'flux': 'mean'},
        detection_probability_points=points,
        detection_probabilities=probs
    )
    ogi_no_survey = Dm.comp_survey.CompSurvey(
        time,
        survey_interval=None,
        survey_speed=150,
        ophrs={'begin': 8, 'end': 17},
        labor=100,
        dispatch_object=rep,
        detection_variables={'flux': 'mean'},
        detection_probability_points=points,
        detection_probabilities=probs
    )
    points = np.logspace(-3, 1, 100)
    probs = 0.5 + 0.5 * np.array([np.math.erf((np.log(f) - np.log(0.474)) / (1.36 * np.sqrt(2))) for f
                                  in points])
    probs[0] = 0
    plane_survey = Dm.site_survey.SiteSurvey(
        time,
        survey_interval=50,
        sites_per_day=200,
        site_cost=100,
        mu=0.1,
        dispatch_object=ogi_no_survey,
        detection_variables={'flux': 'mean'},
        detection_probability_points=points,
        detection_probabilities=probs
    )
    # test __init__
    ogi_survey = Dm.ldar_program.LDARProgram(
        time, copy.deepcopy(gas_field), {'ogi': ogi}
    )
    if len(ogi_survey.find_cost) != 11:
        raise ValueError("find_cost not set to the correct length")
    if np.sum(ogi_survey.emissions.flux) != 100:
        raise ValueError("Unexpected emission rate in LDAR program initialization")

    # test end_emissions
    ogi_survey.emissions.endtime[0] = 0
    ogi_survey.end_emissions(time)
    if ogi_survey.emissions.flux[0] != 0:
        raise ValueError("ldar_program.end_emissions not zeroing emissions as expected")
    # test action
    ogi_survey.action(time, gas_field)
    if np.sum(ogi_survey.emissions.flux) != 84:
        raise ValueError("Unexpected emission rate after LDAR program action")
    # test combined program
    tech_dict = {
        'plane': plane_survey,
        'ogi': ogi_no_survey
    }
    tiered_survey = Dm.ldar_program.LDARProgram(
        time, gas_field, tech_dict
    )
    # test action
    tiered_survey.action(time, gas_field)
    if np.sum(tiered_survey.emissions.flux) != 79:
        raise ValueError("Unexpected emission rate after LDAR program action with tiered survey")


def test_field_simulation():
    gas_field = basic_gas_field()
    timeobj = feast.EmissionSimModules.simulation_classes.Time(delta_t=1, end_time=2)
    rep = Dm.repair.Repair(repair_delay=0)
    points = np.logspace(-3, 1, 100)
    probs = 0.5 + 0.5 * np.array([np.math.erf((np.log(f) - np.log(0.02)) / (0.8 * np.sqrt(2))) for f
                                  in points])
    ogi = Dm.comp_survey.CompSurvey(
        timeobj,
        survey_interval=50,
        survey_speed=150,
        ophrs={'begin': 8, 'end': 17},
        labor=100,
        dispatch_object=rep,
        detection_variables={'flux': 'mean'},
        detection_probability_points=points,
        detection_probabilities=probs
    )
    ogi_no_survey = Dm.comp_survey.CompSurvey(
        timeobj,
        survey_interval=None,
        survey_speed=150,
        ophrs={'begin': 8, 'end': 17},
        labor=100,
        dispatch_object=rep,
        detection_variables={'flux': 'mean'},
        detection_probability_points=points,
        detection_probabilities=probs
    )
    points = np.logspace(-3, 1, 100)
    probs = 0.5 + 0.5 * np.array([np.math.erf((np.log(f) - np.log(0.474)) / (1.36 * np.sqrt(2))) for f
                                  in points])
    plane_survey = Dm.site_survey.SiteSurvey(
        timeobj,
        survey_interval=50,
        sites_per_day=200,
        site_cost=100,
        mu=0.1,
        dispatch_object=ogi_no_survey,
        detection_variables={'flux': 'mean'},
        detection_probability_points=points,
        detection_probabilities=probs
    )
    ogi_survey = Dm.ldar_program.LDARProgram(
        timeobj, copy.deepcopy(gas_field), {'ogi': ogi}
    )
    tech_dict = {
        'plane': plane_survey,
        'ogi': ogi_no_survey
    }
    tiered_survey = Dm.ldar_program.LDARProgram(
        timeobj, gas_field, tech_dict
    )
    feast.field_simulation.field_simulation(
            time=timeobj, gas_field=gas_field,
            ldar_program_dict={'tiered': tiered_survey, 'ogi': ogi_survey},
            dir_out='ResultsTemp', display_status=False
        )

    with open('ResultsTemp/realization0.p', 'rb') as f:
        res = pickle.load(f)
    if res.ldar_program_dict['tiered'].emissions_timeseries[-1] >= \
            res.ldar_program_dict['ogi'].emissions_timeseries[-1]:
        raise ValueError("field_simulation is not returning emission reductions as expected")
    if res.ldar_program_dict['ogi'].emissions_timeseries[-1] >= res.ldar_program_dict['Null'].emissions_timeseries[-1]:
        raise ValueError("field_simulation is not returning emission reductions as expected")

    for f in os.listdir('ResultsTemp'):
        os.remove(os.path.join('ResultsTemp', f))
    try:
        os.rmdir('ResultsTemp')
    except PermissionError:
        # If there is an automated syncing process, a short pause may be necessary before removing "ResultsTemp"
        ti.sleep(5)
        os.rmdir('ResultsTemp')


def test_check_op_envelope():
    gas_field = basic_gas_field()
    gas_field.met_data_path = 'TMY-DataExample.csv'
    time = sc.Time(delta_t=1, end_time=10, current_time=0)
    gas_field.met_data_maker()
    rep = Dm.repair.Repair(repair_delay=0)
    wind_dirs_mins = np.zeros(gas_field.n_sites)
    wind_dirs_maxs = np.ones(gas_field.n_sites) * 90
    tech = Dm.comp_survey.CompSurvey(
        time,
        survey_interval=50,
        survey_speed=150,
        ophrs={'begin': 8, 'end': 17},
        labor=100,
        dispatch_object=rep,
        op_envelope={
            'wind speed': {'class': 1, 'min': 1, 'max': 10},
            'wind direction': {'class': 2, 'min': wind_dirs_mins, 'max': wind_dirs_maxs}
        }
    )
    op_env = tech.check_op_envelope(gas_field, time, 0)
    if op_env != 'site fail':
        raise ValueError("check_op_envelope is not returning 'site fail' as expected")
    wind_dirs_mins = np.zeros([gas_field.n_sites, 2])
    wind_dirs_mins[:, 1] = 145
    wind_dirs_maxs = np.ones([gas_field.n_sites, 2]) * 90
    wind_dirs_maxs[:, 1] += 145
    tech.op_envelope['wind direction'] = {'class': 2, 'min': wind_dirs_mins, 'max': wind_dirs_maxs}
    op_env = tech.check_op_envelope(gas_field, time, 0)
    if op_env != 'site pass':
        raise ValueError("check_op_envelope is not passing as expected")
    tech.op_envelope['wind speed']['max'] = [2]
    op_env = tech.check_op_envelope(gas_field, time, 0)
    if op_env != 'field fail':
        raise ValueError("check_op_envelope is no retruning 'field fail' as expected")


def test_get_current_conditions():
    gas_field = basic_gas_field()
    gas_field.met_data_path = 'TMY-DataExample.csv'
    time = sc.Time(delta_t=1, end_time=10, current_time=0)
    gas_field.met_data_maker()
    rep = Dm.repair.Repair(repair_delay=0)
    prob_points, detect_probs = ex_prob_detect_arrays()
    tech = Dm.comp_survey.CompSurvey(
        time,
        survey_interval=50,
        survey_speed=150,
        ophrs={'begin': 8, 'end': 17},
        labor=100,
        dispatch_object=rep,
        detection_variables={'flux': 'mean', 'wind speed': 'mean'},
        detection_probability_points=prob_points,
        detection_probabilities=detect_probs
    )
    emissions = gas_field.initial_emissions
    emissions.flux = np.linspace(0.1, 10, 100)
    em_indexes = np.linspace(0, emissions.n_leaks - 1, emissions.n_leaks, dtype=int)
    ret = tech.get_current_conditions(time, gas_field, emissions, em_indexes)
    if np.any(ret[:, 0] != emissions.flux[:emissions.n_leaks]):
        raise ValueError("get_current_conditions not returning the correct values")
    if np.any(ret[:, 1] != np.mean(gas_field.met['wind speed'][8:17])):
        raise ValueError("get_current_conditions not returning the correct values")


def test_empirical_interpolator():
    time = sc.Time(delta_t=1, end_time=10, current_time=0)
    rep = Dm.repair.Repair(repair_delay=0)
    prob_points, detect_probs = ex_prob_detect_arrays()
    tech = Dm.comp_survey.CompSurvey(
        time,
        survey_interval=50,
        survey_speed=150,
        ophrs={'begin': 8, 'end': 17},
        labor=100,
        dispatch_object=rep,
        detection_variables={'flux': 'mean', 'wind speed': 'mean'},
        detection_probability_points=prob_points,
        detection_probabilities=detect_probs
    )
    probs = tech.empirical_interpolator(tech.detection_probability_points, tech.detection_probabilities,
                                        np.array([[0.01, 1], [0.05, 1]]))
    if np.abs(probs[0] - 0.24509709) > 1e-5 or np.abs(probs[1] - 0.25784611) > 1e-5:
        raise ValueError("empirical_interpolator is not returning the correct probabilities")
    probs = tech.empirical_interpolator(tech.detection_probability_points, tech.detection_probabilities,
                                        np.array([0.03, 1]))
    if not min(tech.detection_probabilities[:2]) <= probs[0] <= max(tech.detection_probabilities[:2]):
        raise ValueError("empirical_interpolator is not interpolating correctly")
    probs = tech.empirical_interpolator(tech.detection_probability_points, tech.detection_probabilities,
                                        np.array([0.01, 1.5]))
    if not tech.detection_probabilities[0] >= probs[0] >= tech.detection_probabilities[6]:
        raise ValueError("empirical_interpolator is not interpolating correctly")


def test_choose_sites():
    gas_field = basic_gas_field()
    gas_field.met_data_path = 'TMY-DataExample.csv'
    time = sc.Time(delta_t=1, end_time=10, current_time=0)
    gas_field.met_data_maker()
    rep = Dm.repair.Repair(repair_delay=0)
    # wind_dirs_mins = np.zeros(gas_field.n_sites)
    # wind_dirs_maxs = np.ones(gas_field.n_sites) * 90
    tech = Dm.comp_survey.CompSurvey(
        time,
        survey_interval=50,
        survey_speed=150,
        ophrs={'begin': 8, 'end': 17},
        labor=100,
        dispatch_object=rep,
        op_envelope={
            # 'wind speed': {'class': 1, 'min': 1, 'max': 10},
            # 'wind direction': {'class': 2, 'min': wind_dirs_mins, 'max': wind_dirs_maxs}
        }
    )
    tech.site_queue = list(np.linspace(0, gas_field.n_sites - 1, gas_field.n_sites, dtype=int))
    siteinds = tech.choose_sites(gas_field, time, 10)
    if not (siteinds == np.linspace(0, 9, 10, dtype=int)).all():
        raise ValueError("choose_sites() is not selecting the correcting sites")

    tech.site_queue = []
    siteinds = tech.choose_sites(gas_field, time, 10)
    if siteinds:
        raise ValueError("choose_sites() fails for empty site_queue queue")


def test_site_monitor():
    gas_field = basic_gas_field()
    gas_field.met_data_path = 'TMY-DataExample.csv'
    time = sc.Time(delta_t=1, end_time=10, current_time=0)
    gas_field.met_data_maker()
    rep = Dm.repair.Repair(repair_delay=0)
    cm = Dm.site_monitor.SiteMonitor(
        time,
        time_to_detect_points=np.array([0.99, 1.0, 1.01]),
        time_to_detect_days=[np.infty, 1, 0],
        detection_variables={'flux': 'mean'},
        dispatch_object=rep,
    )
    site_inds = list(range(0, 10))
    emissions = copy.copy(gas_field.initial_emissions)
    detect = cm.detect_prob_curve(time, gas_field, site_inds, emissions)
    must_detect = [0, 9, 3]
    must_not_detect = [2, 7, 8]
    for md in must_detect:
        if md not in detect:
            raise ValueError("site_monitor.detect_prob_curve not flagging the correct sites")
    for mnd in must_not_detect:
        if mnd in detect:
            raise ValueError("site_monitor.detect_prob_curve flagging sites that it should not")
    ttd_list = []
    ttd = 0
    time.delta_t = 0.1
    for ind in range(1000):
        ttd += time.delta_t
        detect = cm.detect_prob_curve(time, gas_field, site_inds, emissions)
        if 1 in detect:
            ttd_list.append(ttd)
            ttd = 0
    if np.abs(np.mean(ttd_list) - 1) > 0.5:
        raise ValueError("Mean time to detection deviates from expected value by >5 sigma in site_monitor test")


test_repair()
test_comp_survey()
test_check_time()
test_site_survey()
test_ldar_program()
test_field_simulation()
test_check_op_envelope()
test_sitedetect_sites_surveyed()
test_comp_survey_emitters_surveyed()
test_get_current_conditions()
test_empirical_interpolator()
test_choose_sites()
test_site_monitor()


print("Successfully completed LDAR tests.")
