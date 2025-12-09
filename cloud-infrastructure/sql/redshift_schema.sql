-- ECU Diagnostics Redshift Schema
-- Star schema design for vehicle telemetry analytics

-- Dimension: Vehicles
CREATE TABLE IF NOT EXISTS dim_vehicles (
    vehicle_key INTEGER IDENTITY(1,1) PRIMARY KEY,
    vin VARCHAR(17) UNIQUE NOT NULL,
    make VARCHAR(50),
    model VARCHAR(50),
    year INTEGER,
    firmware_version VARCHAR(20),
    created_at TIMESTAMP DEFAULT GETDATE(),
    updated_at TIMESTAMP DEFAULT GETDATE()
) DISTSTYLE ALL
SORTKEY (vin);

-- Fact: Telemetry
CREATE TABLE IF NOT EXISTS fact_telemetry (
    telemetry_key BIGINT IDENTITY(1,1) PRIMARY KEY,
    vehicle_key INTEGER REFERENCES dim_vehicles(vehicle_key),
    timestamp TIMESTAMP NOT NULL,
    parameter_name VARCHAR(50) NOT NULL,
    parameter_value DOUBLE PRECISION,
    unit VARCHAR(20),
    telemetry_type VARCHAR(20),
    created_at TIMESTAMP DEFAULT GETDATE()
) DISTKEY(vehicle_key)
SORTKEY(timestamp, vehicle_key);

-- Fact: DTCs (Diagnostic Trouble Codes)
CREATE TABLE IF NOT EXISTS fact_dtcs (
    dtc_key BIGINT IDENTITY(1,1) PRIMARY KEY,
    vehicle_key INTEGER REFERENCES dim_vehicles(vehicle_key),
    timestamp TIMESTAMP NOT NULL,
    dtc_code VARCHAR(10) NOT NULL,
    status_byte INTEGER,
    severity VARCHAR(20),
    description TEXT,
    resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT GETDATE()
) DISTKEY(vehicle_key)
SORTKEY(timestamp, vehicle_key);

-- Fact: Anomalies
CREATE TABLE IF NOT EXISTS fact_anomalies (
    anomaly_key BIGINT IDENTITY(1,1) PRIMARY KEY,
    vehicle_key INTEGER REFERENCES dim_vehicles(vehicle_key),
    timestamp TIMESTAMP NOT NULL,
    subsystem VARCHAR(50) NOT NULL,
    anomaly_type VARCHAR(50) NOT NULL,
    severity_score DOUBLE PRECISION,
    ml_score DOUBLE PRECISION,
    detection_method VARCHAR(50),
    acknowledged BOOLEAN DEFAULT FALSE,
    acknowledged_by VARCHAR(100),
    acknowledged_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT GETDATE()
) DISTKEY(vehicle_key)
SORTKEY(timestamp, vehicle_key);

-- Fact: OTA Updates
CREATE TABLE IF NOT EXISTS fact_ota_updates (
    ota_key BIGINT IDENTITY(1,1) PRIMARY KEY,
    vehicle_key INTEGER REFERENCES dim_vehicles(vehicle_key),
    update_id VARCHAR(50) NOT NULL,
    ecu_address VARCHAR(10),
    ecu_name VARCHAR(100),
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP,
    status VARCHAR(20) NOT NULL,
    from_version VARCHAR(20),
    to_version VARCHAR(20),
    download_progress INTEGER,
    install_progress INTEGER,
    verification_status VARCHAR(20),
    error_message TEXT,
    created_at TIMESTAMP DEFAULT GETDATE()
) DISTKEY(vehicle_key)
SORTKEY(start_time, vehicle_key);

-- Fact: ECU Performance Metrics
CREATE TABLE IF NOT EXISTS fact_ecu_performance (
    performance_key BIGINT IDENTITY(1,1) PRIMARY KEY,
    vehicle_key INTEGER REFERENCES dim_vehicles(vehicle_key),
    timestamp TIMESTAMP NOT NULL,
    ecu_address VARCHAR(10) NOT NULL,
    cpu_utilization DOUBLE PRECISION,
    memory_usage DOUBLE PRECISION,
    response_time DOUBLE PRECISION,
    reset_count INTEGER,
    created_at TIMESTAMP DEFAULT GETDATE()
) DISTKEY(vehicle_key)
SORTKEY(timestamp, vehicle_key);

-- Create indexes for common queries
CREATE INDEX idx_telemetry_timestamp ON fact_telemetry(timestamp);
CREATE INDEX idx_telemetry_parameter ON fact_telemetry(parameter_name);
CREATE INDEX idx_dtcs_code ON fact_dtcs(dtc_code);
CREATE INDEX idx_dtcs_severity ON fact_dtcs(severity);
CREATE INDEX idx_anomalies_subsystem ON fact_anomalies(subsystem);
CREATE INDEX idx_anomalies_acknowledged ON fact_anomalies(acknowledged);
CREATE INDEX idx_ota_status ON fact_ota_updates(status);

-- Create views for common queries

-- View: Latest vehicle telemetry
CREATE OR REPLACE VIEW v_latest_telemetry AS
SELECT 
    v.vin,
    v.make,
    v.model,
    t.parameter_name,
    t.parameter_value,
    t.unit,
    t.timestamp
FROM fact_telemetry t
JOIN dim_vehicles v ON t.vehicle_key = v.vehicle_key
WHERE t.timestamp > DATEADD(hour, -1, GETDATE());

-- View: Active DTCs
CREATE OR REPLACE VIEW v_active_dtcs AS
SELECT 
    v.vin,
    v.make,
    v.model,
    d.dtc_code,
    d.severity,
    d.description,
    d.timestamp
FROM fact_dtcs d
JOIN dim_vehicles v ON d.vehicle_key = v.vehicle_key
WHERE d.resolved = FALSE
ORDER BY d.timestamp DESC;

-- View: Unacknowledged anomalies
CREATE OR REPLACE VIEW v_unacknowledged_anomalies AS
SELECT 
    v.vin,
    v.make,
    v.model,
    a.subsystem,
    a.anomaly_type,
    a.severity_score,
    a.timestamp
FROM fact_anomalies a
JOIN dim_vehicles v ON a.vehicle_key = v.vehicle_key
WHERE a.acknowledged = FALSE
ORDER BY a.severity_score DESC, a.timestamp DESC;

-- View: Recent OTA updates
CREATE OR REPLACE VIEW v_recent_ota_updates AS
SELECT 
    v.vin,
    v.make,
    v.model,
    o.update_id,
    o.ecu_name,
    o.from_version,
    o.to_version,
    o.status,
    o.start_time,
    o.end_time,
    DATEDIFF(minute, o.start_time, o.end_time) as duration_minutes
FROM fact_ota_updates o
JOIN dim_vehicles v ON o.vehicle_key = v.vehicle_key
WHERE o.start_time > DATEADD(day, -7, GETDATE())
ORDER BY o.start_time DESC;

-- Grant permissions (adjust as needed)
GRANT SELECT ON ALL TABLES IN SCHEMA public TO GROUP analytics_users;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO GROUP dashboard_users;
