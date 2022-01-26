import sys, os
from lxml import etree as ET
import psycopg2


sumo_rel_path = 'sumo'

buildings_file = os.path.join(sumo_rel_path, 'config', 'buildings.xml')


def get_buildings():
    osm = ET.parse(os.path.join(sumo_rel_path, buildings_file))
    return [tuple([n.text for n in e.getchildren()]) for e in osm.xpath('building')]


def load_buildings_to_db(buildings):
    try:
        conn = psycopg2.connect("dbname=agh user=postgres password=letMEin!")
        cur = conn.cursor()

        sql = 'DELETE FROM buildings; INSERT INTO buildings(name, lon, lat) VALUES(%s, %s, %s)'
        cur.executemany(sql, buildings)
        
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        print(error)
    finally:
        if conn is not None:
            conn.close()


def main():
    buildings = get_buildings()
    load_buildings_to_db(buildings)


if __name__ == '__main__':
    main()
