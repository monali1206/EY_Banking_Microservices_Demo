#!/bin/bash
set -e

echo "Initializing Databases..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "postgres" <<-EOSQL
    CREATE DATABASE kyc_db;
    CREATE DATABASE pan_db;
    CREATE DATABASE aadhaar_db;
    GRANT ALL PRIVILEGES ON DATABASE kyc_db TO $POSTGRES_USER;
    GRANT ALL PRIVILEGES ON DATABASE pan_db TO $POSTGRES_USER;
    GRANT ALL PRIVILEGES ON DATABASE aadhaar_db TO $POSTGRES_USER;
EOSQL
echo "Databases created successfully."