FROM postgres:latest

RUN apt-get update \
 && apt-get -y install apt-utils \
 && apt-get -y install expat \
 && apt-get -y install libexpat1-dev \
 && apt-get -y install libboost-dev \
 && apt-get -y install libboost-program-options-dev \
 && apt -y install libpqxx-dev \
 && apt-get -y install git \
 && apt-get -y install build-essential \
 && apt-get -y install cmake \
 && apt-get -y install net-tools

RUN git clone https://github.com/pgRouting/osm2pgrouting.git \
 && cd osm2pgrouting \
 && cmake -H. -Bbuild \
 && cd build \
 && make \
 && make install

RUN mkdir data conf
COPY ./data/* /data/
COPY ./conf/* /conf/

CMD ["osm2pgrouting", "--f", "/data/agh_bbox.osm.xml", "--conf", "/conf/mapconfig.xml", "--dbname", "agh", "--username", "postgres", "--password", "letMEin!", "--clean"]

#ENTRYPOINT [ "osm2pgrouting --f data/Cracow.osm --conf /conf/mapconfig.xml --dbname osm --username postgres --password letMEin! --clean" ]