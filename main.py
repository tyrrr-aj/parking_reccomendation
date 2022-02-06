import os, sys, random
from time import sleep
import traci
from traci.exceptions import FatalTraCIError, TraCIException
from lxml import etree as ET
import click


from parking_advisor import ParkingAdvisor
from time_controller import TimeController
from logger import Logger
from constants import *


if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    sys.exit("please declare environment variable 'SUMO_HOME'")


sumocfg_path = os.path.join(sumo_rel_path, config_subdir, sumocfg_filename)
users_file = os.path.join(sumo_rel_path, config_subdir, users_conf_filename)
parkings_file = os.path.join(sumo_rel_path, gen_subdir, parkings_gen_filename)


def evaluate_target_suggestions(true_target, suggested_targets, logger):
    # based on position (and presence) of true target on propositions list, may be logged or printed
    logger.log(f'suggested: {suggested_targets}\n true: {true_target}')


def read_true_target(vehicle, users):
    return users.xpath(f'./user/trips/trip[@id="{vehicle}"]')[0].attrib['target']


def guide_vehicles(advisor, users, parking_tree, gui, logger):
    new_vehicle_ids = traci.simulation.getDepartedIDList()
    new_guided_vehicle_ids = [vehicle_id for vehicle_id in new_vehicle_ids if traci.vehicle.getTypeID(vehicle_id) == 'veh_guided']
    
    for guided_veh in new_guided_vehicle_ids:
        traci.vehicle.highlight(guided_veh)
        
        suggested_targets = advisor.suggest_targets(guided_veh)
        true_target = read_true_target(guided_veh, users)
        evaluate_target_suggestions(true_target, suggested_targets, logger)

        parking_areas = advisor.pick_parking_areas(guided_veh, true_target)
        for parking_area in parking_areas:
            parking_area_elem = parking_tree.xpath(f'./parkingArea[@id="{parking_area}"]')[0]
            traci.vehicle.setVia(guided_veh, parking_area_elem.attrib['lane'].split('_')[0])
            traci.vehicle.rerouteTraveltime(guided_veh)
            try:
                traci.vehicle.setParkingAreaStop(guided_veh, parking_area, duration=random.randint(MIN_STOP_TIME_SEC, MAX_STOP_TIME_SEC))
                logger.log(f'Sending vehicle {guided_veh} to parking {parking_area}\n')
                break
            except TraCIException:
                pass
        else:
            logger.log(f'WARNING: Failed to send vehicle {guided_veh} to applicable parking area')

    if gui and new_guided_vehicle_ids:
        traci.gui.trackVehicle('View #0', new_guided_vehicle_ids[0])
        traci.gui.setZoom('View #0', 1000)
        # sleep(1)


@click.command()
@click.option('--gui/--headless', default=True, help='Run simulation with/without GUI.')
@click.option('-q', '--quiet', default=False, help='Silence log output in terminal.', is_flag=True)
@click.option('-o', '--output', default='', help='File to which log should be saved.')
@click.option('-c', '--continue', 'continue_', default=False, is_flag=True, help='Continue simulation from when it ended during last run.')
@click.option('-w', '--week', default=1, help='Week at which simulation starts (positive integer).')
@click.option('-d', '--day', default=1, help='Day of week at which simulation starts (1-7).')
@click.option('-t', '--time', default='00:00:00', help='Time at which simulation starts, in format hh:mm:ss.')
@click.option('--clear', default=False, is_flag=True, help='Cleares users history and stored simulation time.')
def main(gui, quiet, output, continue_, week, day, time, clear):
    if gui:
        traci.start(['sumo-gui', '-c', sumocfg_path])
    else:
        traci.start(['sumo', '-c', sumocfg_path])

    users = ET.parse(users_file)
    parking_tree = ET.parse(parkings_file)

    time_controller = TimeController(continue_, week, day, time)
    advisor = ParkingAdvisor(time_controller)
    logger = Logger(quiet, output)
    step = 0

    if clear:
        advisor.clear_user_history()
        time_controller.clear_stored_time()

    try:
        while traci.simulation.getMinExpectedNumber() > 0:
            traci.simulationStep()
            time_controller.update_curr_time(traci.simulation.getTime())
            guide_vehicles(advisor, users, parking_tree, gui, logger)
            step += 1

    except FatalTraCIError as e:
        print(f'simulation interrupted (stopped by TraCI) at step {step}')
        print(e)
        return -1

    finally:
        time_controller.save_time()


if __name__ == '__main__':
    sys.exit(main())
