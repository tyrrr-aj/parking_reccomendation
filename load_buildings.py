import imp
import os
from lxml import etree as ET
import psycopg2


from constants import *

buildings_file = os.path.join(sumo_rel_path, config_subdir, buildings_filename)


def get_buildings():
    buildings_tree = ET.parse(buildings_file)
    return [tuple([n.text for n in e.getchildren()]) for e in buildings_tree.xpath('/buildings/building')]


def load_buildings_to_db(buildings):
    try:
        conn = psycopg2.connect(conn_string)
        cur = conn.cursor()

        sql = 'DELETE FROM buildings; '
        cur.execute(sql)

        sql = 'INSERT INTO buildings(name, lon, lat) VALUES(%s, %s, %s)'
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
