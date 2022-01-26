import os, sys, random
from time import sleep
import traci
from traci.exceptions import FatalTraCIError, TraCIException
from lxml import etree as ET
from parking_advisor import ParkingAdvisor

if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    sys.exit("please declare environment variable 'SUMO_HOME'")


min_stop_time = 200
max_stop_time = 2000

sumo_rel_path = 'sumo'
users_file = os.path.join('config', 'users.xml')
parkings_file = os.path.join('generated', 'parkings.add.xml')


def evaluate_target_suggestions(true_target, suggested_targets):
    # based on position (and presence) of true target on propositions list, may be logged or printed
    ...


def read_true_target(vehicle, users):
    return users.xpath(f'./user/trips/trip[@id="{vehicle}"]')[0].attrib['target']


def guide_vehicles(advisor, users, parking_tree):
    new_vehicle_ids = traci.simulation.getDepartedIDList()
    new_guided_vehicle_ids = [vehicle_id for vehicle_id in new_vehicle_ids if traci.vehicle.getTypeID(vehicle_id) == 'veh_guided']
    
    for guided_veh in new_guided_vehicle_ids:
        traci.vehicle.highlight(guided_veh)
        
        suggested_targets = advisor.suggest_targets(guided_veh)
        true_target = read_true_target(guided_veh, users)
        evaluate_target_suggestions(true_target, suggested_targets)

        parking_areas = advisor.pick_parking_areas(guided_veh, true_target)
        for parking_area in parking_areas:
            parking_area_elem = parking_tree.xpath(f'./parkingArea[@id="{parking_area}"]')[0]
            traci.vehicle.setVia(guided_veh, parking_area_elem.attrib['lane'].split('_')[0])
            traci.vehicle.rerouteTraveltime(guided_veh)
            try:
                traci.vehicle.setParkingAreaStop(guided_veh, parking_area, duration=random.randint(min_stop_time, max_stop_time))
                print(f'Sending vehicle {guided_veh} to parking {parking_area}')
                break
            except TraCIException:
                pass
        else:
            print(f'WARNING: Failed to send vehicle {guided_veh} to applicable parking area')

    if new_guided_vehicle_ids:
        traci.gui.trackVehicle('View #0', new_guided_vehicle_ids[0])
        traci.gui.setZoom('View #0', 1000)
        sleep(1)


def main():
    traci.start(['sumo-gui', '-c', os.path.join(sumo_rel_path, 'config', 'agh.sumocfg')])
    # traci.start(['sumo', '-c', os.path.join(sumo_rel_path, 'config', 'agh.sumocfg')])

    users = ET.parse(os.path.join(sumo_rel_path, users_file))
    parking_tree = ET.parse(os.path.join(sumo_rel_path, parkings_file))

    advisor = ParkingAdvisor()
    step = 0

    try:
        while traci.simulation.getMinExpectedNumber() > 0:
            traci.simulationStep()
            guide_vehicles(advisor, users, parking_tree)
            step += 1

    except FatalTraCIError as e:
        print(f'simulation interrupted (stopped by TraCI) at step {step}')
        print(e)
        return -1


if __name__ == '__main__':
    sys.exit(main())
