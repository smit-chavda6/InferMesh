#!/bin/sh
# Runs once, on first init of the postgres data volume. Creates the database the
# test suite uses (TEST_DATABASE_URL) alongside the main one.
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    SELECT 'CREATE DATABASE gateway_test'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'gateway_test')\gexec
EOSQL
