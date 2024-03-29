CREATE EXTENSION POSTGIS;
CREATE EXTENSION PGROUTING;

create table ways(
    gid bigint,
    osm_id bigint,
    tag_id integer,
    length double precision,
    length_m double precision,
    name text,
    source bigint,
    target bigint,
    source_osm bigint,
    target_osm bigint,
    cost double precision,
    reverse_cost double precision,
    cost_s double precision,
    reverse_cost_s double precision,
    rule text,
    one_way integer,
    oneway text,
    x1 double precision,
    y1 double precision,
    x2 double precision,
    y2 double precision,
    maxspeed_forward double precision,
    maxspeed_backward double precision,
    priority double precision,
    the_geom geometry(LineString,4326)
);

create table parkings(id varchar(50) primary key, road_id);

create table buildings(
    name varchar(10) primary key, 
    lon float, 
    lat float, 
    geom geometry generated always as (ST_TRANSFORM(ST_SetSRID(ST_Point(lon, lat), 4326), 2178)) stored
);

create table user_history(
    user_id varchar(5), 
    building varchar(10) references buildings(name), 
    time_of_week integer, 
    absolute_time bigint, 
    primary key (user_id, absolute_time)
);


create or replace function get_parkings_around_point(target_point geometry, n int)
returns table(
    id varchar(50),
    dist float
)
language plpgsql
as $$
begin
    return query
    select p.id, min(target_point <-> ST_Transform(w.the_geom, 2178)) as dist 
    from parkings p 
        join ways w on p.road_id = w.osm_id
    group by p.id
    order by dist
    limit n;
end; $$;


create or replace function get_nearest_parkings(target_lon float, target_lat float, n int)
returns table(
    id varchar(50),
    dist float
)
language plpgsql
as $$
declare
    target_coords geometry := ST_Transform(ST_SetSRID(ST_Point(target_lon, target_lat), 4326), 2178);
begin
    return query
    select p.id, p.dist from get_parkings_around_point(target_coords, n) p;
end; $$;


create or replace function get_parkings_around_building(building varchar(10), n int)
returns table(
    id varchar(50),
    dist float
)
language plpgsql
as $$
declare
    target_coords geometry := (select b.geom from buildings b where b.name = building);
begin
    return query
    select p.id, p.dist from get_parkings_around_point(target_coords, n) p;
end; $$;


create or replace function get_events_within_timeframe(
    sought_user_id varchar(5), 
    curr_time_of_week int,
    lon float,
    lat float,
    t_const int,
    neg_time_delta int, 
    pos_time_delta int)
returns table(
    building varchar(10),
    absolute_time bigint,
    time_of_week int
)
language plpgsql
as $$
begin
    return query
    select uh.building, uh.absolute_time, uh.time_of_week
    from user_history uh
    where 
        uh.user_id = sought_user_id 
        and curr_time_of_week + estimated_travel_time(uh.building, lon, lat) + t_const - uh.time_of_week < neg_time_delta
        and uh.time_of_week - (curr_time_of_week + estimated_travel_time(uh.building, lon, lat) + t_const) < pos_time_delta;
end; $$;


create or replace function get_nearby_buildings(
    lon float,
    lat float,
    max_dist float
)
returns table(
    building varchar(10),
    distance float
)
language plpgsql
as $$
declare
    loc geometry = ST_Transform(ST_SetSRID(ST_Point(lon, lat), 4326), 2178);
begin
    return query
    select name, ST_Distance(loc, geom) as distance from buildings where ST_DWithin(loc, geom, max_dist);
end; $$;

create or replace function estimated_travel_time(building varchar(10), lon float, lat float)
returns integer
language plpgsql
as $$
declare
    loc geometry = ST_SetSRID(ST_Point(lon, lat), 4326);
    building_loc geometry;
    vertex_near_loc int;
    vertex_near_building int;
    estimated_time float;
begin
    select ST_Transform(geom, 4326) into building_loc
    from buildings 
    where name = building;

    select id into vertex_near_loc
    from ways_vertices_pgr 
    order by loc <-> the_geom 
    limit 1;

    select id into vertex_near_building
    from ways_vertices_pgr
    order by building_loc <-> the_geom 
    limit 1;

    select agg_cost into estimated_time
    from pgr_dijkstraCost(
        'select gid as id, source, target, cost_s as cost, reverse_cost_s as reverse_cost from ways', vertex_near_loc, vertex_near_building);

    return estimated_time;
end; $$;


create or replace function estimated_driving_time(parking varchar(50), lon float, lat float)
returns integer
language plpgsql
as $$
declare
    loc geometry = ST_SetSRID(ST_Point(lon, lat), 4326);
    parking_loc geometry;
    vertex_near_loc int;
    vertex_near_parking int;
    estimated_time float;
begin
    select ST_Transform(w.the_geom, 4326) into parking_loc
    from parkings p
        join ways w on p.road_id = w.osm_id 
    where p.id = parking;

    select id into vertex_near_loc
    from ways_vertices_pgr 
    order by loc <-> the_geom 
    limit 1;

    select id into vertex_near_parking
    from ways_vertices_pgr
    order by parking_loc <-> the_geom 
    limit 1;

    select agg_cost into estimated_time
    from pgr_dijkstraCost(
        'select gid as id, source, target, cost_s as cost, reverse_cost_s as reverse_cost from ways', vertex_near_loc, vertex_near_parking);

    return estimated_time;
end; $$;


create or replace function estimated_walking_time(parking varchar(50), building varchar(10))
returns integer
language plpgsql
as $$
declare
    building_loc geometry;
    parking_loc geometry;
    vertex_near_building int;
    vertex_near_parking int;
    estimated_time float;
begin
    select ST_Transform(w.the_geom, 4326) into parking_loc
    from parkings p
        join ways w on p.road_id = w.osm_id 
    where p.id = parking;

    select ST_Transform(geom, 4326) into building_loc
    from buildings 
    where name = building;

    select id into vertex_near_building
    from ways_vertices_pgr 
    order by building_loc <-> the_geom 
    limit 1;

    select id into vertex_near_parking
    from ways_vertices_pgr
    order by parking_loc <-> the_geom 
    limit 1;

    select agg_cost into estimated_time
    from pgr_dijkstraCost(
        'select gid as id, source, target, length_m / 1.5 as cost, length_m / 1.5 as reverse_cost from ways', vertex_near_parking, vertex_near_building);

    return estimated_time;
end; $$;


create or replace function estimated_total_time(parking varchar(50), building varchar(10), lon float, lat float)
returns integer
language plpgsql
as $$
begin
    return estimated_driving_time(parking, lon, lat) + estimated_walking_time(parking, building);
end; $$;
