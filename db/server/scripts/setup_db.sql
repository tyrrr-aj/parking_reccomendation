create table parkings(id varchar(50), road_id bigint)

create or replace function get_nearest_parkings(target_lon float, target_lat float)
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
    select p.id, target_coords <-> ST_Transform(w.the_geom, 2178) as dist 
    from parkings p 
        join ways w on p.road_id = w.osm_id 
    order by target_coords <-> ST_Transform(w.the_geom, 2178) 
    limit 10;
end; $$