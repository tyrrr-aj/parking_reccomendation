import sys, os
from lxml import etree as ET
import xml.dom.minidom
import random
import psycopg2


sumo_rel_path = 'sumo'

input_file = os.path.join('generated', 'agh_bbox.osm.xml')
output_file = os.path.join('generated', 'parkings.add.xml')
net_file = os.path.join('generated', 'osm.net.xml')
random_trips_file = os.path.join('generated', 'agh.random.trips.xml')

encoding = 'UTF-8'

vehicle_length = 5.0    # in meters
space_width = 3.2   # in meters
space_length = 5.5  # in meters

min_stop_time = 500
max_stop_time = 2000
stopping_rate = 1
time_base = 3600

n_guided_vehicles = 500

standalone_parking_index = 0


def output_core():
    root = ET.Element('additional')
    # root.set('xmlns:xsi', 'http://www.w3.org/2001/XMLSchema-instance')
    # root.set('xsi:noNamespaceSchemaLocation', 'http://sumo.dlr.de/xsd/additional_file.xsd')
    return root
    

def save_output(output_tree, output=output_file):
    dom = xml.dom.minidom.parseString(ET.tostring(output_tree))
    xml_string = dom.toprettyxml()
    part1, part2 = xml_string.split('?>')

    with open(output, 'w', encoding=encoding) as out:
        out.write(part1 + 'encoding=\"{}\"?>\n'.format(encoding) + part2)


def add_roadside_parking(way, side, net_tree, output_tree):
    id = way.attrib['id']
    side_modifier = '-' if side == 'left' else ''
    parking_kind = way.xpath(f'./tag[@k="parking:lane:{side}" or @k="parking:lane:both"]')[0].attrib['v']

    lanes = net_tree.xpath(f'//edge/lane[starts-with(@id, "{side_modifier}{id}")]')
    for lane in lanes:
        parking = ET.SubElement(output_tree, 'parkingArea')
        parking.set('id', f'parking_roadside_{lane.attrib["id"]}')
        parking.set('lane', lane.attrib["id"])
        parking.set('startPos', '0.0')
        parking.set('endPos', lane.attrib['length'])
        parking.set('roadsideCapacity', str(int(float(lane.attrib['length']) // vehicle_length)))

        if parking_kind == 'perpendicular':
            parking.set('angle', '90.0')
        elif parking_kind == 'diagonal':
            parking.set('angle', '60.0')


def add_standalone_parking(way, net_tree, output_tree):
    way_id = way.attrib['id']
    lanes = net_tree.xpath(f'//edge/lane[starts-with(@id, "{way_id}") or starts-with(@id, "-{way_id}")]')
    if lanes:
        lane = lanes[0]
        parking = ET.SubElement(output_tree, 'parkingArea')
        parking.set('id', f'parking_standalone_{standalone_parking_index}')
        parking.set('lane', lane.attrib["id"])
        parking.set('startPos', '0.0')
        parking.set('endPos', lane.attrib['length'])
        parking.set('angle', '90.0')

        spaces = way.xpath('./nd')
        for space_elem in spaces:
            space = ET.SubElement(parking, 'space')
            space.set('x', space_elem.attrib['lon'])
            space.set('y', space_elem.attrib['lat'])
            space.set('width', space_width)
            space.set('length', space_length)
    # else:
        # print(f'WARNING: no lanes found for way {way_id}')


def add_parking_along_aisle(way, net_tree, output_tree):
    id = way.attrib['id']

    lanes = net_tree.xpath(f'//edge/lane[starts-with(@id, "{id}") or starts-with(@id, "-{id}")]')
    for lane in lanes:
        parking = ET.SubElement(output_tree, 'parkingArea')
        parking.set('id', f'parking_aisle_{lane.attrib["id"]}')
        parking.set('lane', lane.attrib["id"])
        parking.set('startPos', '0.0')
        parking.set('endPos', lane.attrib['length'])
        parking.set('roadsideCapacity', str(int(float(lane.attrib['length']) // space_width)))
        parking.set('angle', '90.0')


def add_parkings_along_roads(input_tree, net_tree, output_tree):
    ways_with_parking_on_left = input_tree.xpath('//way[./tag[(@k="parking:lane:left" or @k="parking:lane:both") and @v!="no_stopping" and @v!="no"]]')
    ways_with_parking_on_right = input_tree.xpath('//way[./tag[(@k="parking:lane:right" or @k="parking:lane:both") and @v!="no_stopping" and @v!="no"]]')

    for way in ways_with_parking_on_left:
        add_roadside_parking(way, 'left', net_tree, output_tree)

    for way in ways_with_parking_on_right:
        add_roadside_parking(way, 'right', net_tree, output_tree)


def add_standalone_parkings(input_tree, net_tree, output_tree):
    ways_with_standalone_parking = input_tree.xpath('//way[./tag[@k="amenity" and @v="parking"]]')

    for way in ways_with_standalone_parking:
        add_standalone_parking(way, net_tree, output_tree)


def add_parkings_along_aisles(input_tree, net_tree, output_tree):
    parking_aisles = input_tree.xpath('//way[./tag[@k="service" and @v="parking_aisle"]]')
    for aisle in parking_aisles:
        add_parking_along_aisle(aisle, net_tree, output_tree)


def add_stops_to_random_trips(trips_tree, output_tree):
    parkings = output_tree.xpath('/additional/parkingArea')
    trips = trips_tree.xpath('/routes/trip')

    parking_assignments = random.choices(parkings, weights=[int(parking.attrib['roadsideCapacity']) for parking in parkings], k=len(trips))
    for i, trip, parking in zip(range(len(trips)), trips, parking_assignments):
        stop = ET.SubElement(trip, 'stop')
        stop.set('parkingArea', parking.attrib['id'])
        stop.set('duration', str(random.randint(min_stop_time, max_stop_time)))
        # trip.set('via', parking.attrib['lane'].split('_')[0])
        trip.set('depart', str(float(trip.attrib['depart']) + time_base * (i % stopping_rate)))

    all_trips = trips_tree.find('.')
    all_trips[:] = sorted(all_trips, key=lambda trip: float(trip.attrib['depart']) if trip.tag == 'trip' else 0.0)


def add_parkings_to_db(output_tree):
    try:
        conn = psycopg2.connect("dbname=agh user=postgres password=letMEin!")
        cur = conn.cursor()

        sql = 'INSERT INTO parkings(id, road_id) VALUES(%s, %s)'

        road_id = lambda lane_id: int(lane_id.split('#')[0].split('_')[0].split('-')[-1])
        values = [(parking.attrib['id'], road_id(parking.attrib['lane'])) for parking in output_tree.xpath('/additional/parkingArea')]

        cur.executemany(sql, values)
        
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        print(error)
    finally:
        if conn is not None:
            conn.close()


def pick_guided_vehicles(trips_tree):
    all_trips = trips_tree.xpath('/routes/trip')
    picked_trips = random.choices(all_trips, k=n_guided_vehicles)
    for guided_trip in picked_trips:
        guided_trip.set('type', 'veh_guided')
        stop = guided_trip.find('stop')
        if stop is not None:
            guided_trip.remove(stop)


def main():
    output_tree = output_core()
    input_tree = ET.parse(os.path.join(sumo_rel_path, input_file))
    net_tree = ET.parse(os.path.join(sumo_rel_path, net_file))
    trips_tree = ET.parse(os.path.join(sumo_rel_path, random_trips_file))

    add_parkings_along_roads(input_tree, net_tree, output_tree)
    add_standalone_parkings(input_tree, net_tree, output_tree)
    add_parkings_along_aisles(input_tree, net_tree, output_tree)

    add_parkings_to_db(output_tree)
    
    # add_guided_v_type(trips_tree)
    add_stops_to_random_trips(trips_tree, output_tree)
    # pick_guided_vehicles(trips_tree)

    save_output(output_tree)
    save_output(trips_tree, output=os.path.join(sumo_rel_path, random_trips_file))


if __name__ == '__main__':
    sys.exit(main())
