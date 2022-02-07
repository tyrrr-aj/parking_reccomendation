FROM postgis/postgis

COPY ./scritps/setup_db.sql /
RUN psql -U postgres -c 'create database agh;' \
    && psql -U postgres -d agh -a -f /setup_db.sql