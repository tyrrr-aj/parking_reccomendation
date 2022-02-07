docker run -d -p 5432:5432 --name parking-rec tyrrr/parking_recommendation_db:latest
docker run --name agh_map_loader tyrrr/parking_recommendation_map_loader:latest
docker stop agh_map_loader
docker stop parking-rec

pipenv run python "%SUMO_HOME%\tools\osmGet.py" --bbox "19.9,50.0635,19.9254,50.0706" --output-dir ./sumo/generated --prefix agh
pipenv run python "%SUMO_HOME%\tools\osmBuild.py" --osm-file ./sumo/generated/agh_bbox.osm.xml --netconvert-typemap "./sumo/generated/osmNetconvert.typ.xml" --typemap "%SUMO_HOME%data\typemap\osmPolyconvert.typ.xml" --output-dir .