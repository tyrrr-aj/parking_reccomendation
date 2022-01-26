create table parkings(id varchar(50), road_id bigint);
create table buildings(
    name varchar(10), 
    lon float, 
    lat float, 
    geom geometry generated always as (ST_TRANSFORM(ST_SetSRID(ST_Point(lon, lat), 4326), 2178)) stored
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
    select p.id, target_point <-> ST_Transform(w.the_geom, 2178) as dist 
    from parkings p 
        join ways w on p.road_id = w.osm_id 
    order by target_point <-> ST_Transform(w.the_geom, 2178) 
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
