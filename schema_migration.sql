-- ============================================================================
-- Student Drowsiness Alert System — In-Place Database Migration Script
-- Purpose: Upgrades an existing student monitoring schema (Student, Sessions, Device, Alert)
-- to the full ER Diagram architecture WITHOUT dropping existing tables or data.
-- ============================================================================

SET ECHO ON;
SET FEEDBACK ON;

PROMPT Starting the non-destructive student monitoring schema migration...

-- 1. Extend Student Table (Add department column if missing)
BEGIN
    EXECUTE IMMEDIATE 'ALTER TABLE Student ADD (department VARCHAR2(50) DEFAULT ''CSE'')';
EXCEPTION WHEN OTHERS THEN NULL;
END;
/

-- 2. Extend Sessions Table (Add proctor_id foreign key column if missing)
BEGIN
    EXECUTE IMMEDIATE 'ALTER TABLE Sessions ADD (proctor_id VARCHAR2(15))';
EXCEPTION WHEN OTHERS THEN NULL;
END;
/

-- 3. Extend Device Table (Add health_score column if missing)
BEGIN
    EXECUTE IMMEDIATE 'ALTER TABLE Device ADD (health_score NUMBER DEFAULT 98)';
EXCEPTION WHEN OTHERS THEN NULL;
END;
/

-- 4. Extend Alert Table (Add status, eye_closure_sec, resolution columns)
BEGIN
    EXECUTE IMMEDIATE 'ALTER TABLE Alert ADD (
        status VARCHAR2(15) DEFAULT ''Pending'' CHECK (status IN (''Pending'', ''Acknowledged'', ''Resolved'')),
        eye_closure_sec NUMBER(4,1) DEFAULT 0.0,
        resolution_notes VARCHAR2(255),
        resolved_by VARCHAR2(50),
        resolved_at DATE
    )';
EXCEPTION WHEN OTHERS THEN NULL;
END;
/

-- 5. Create New ER Diagram Tables If Not Existing
BEGIN
    EXECUTE IMMEDIATE 'CREATE TABLE Users (
        user_id       NUMBER PRIMARY KEY,
        username      VARCHAR2(50) NOT NULL UNIQUE,
        password_hash VARCHAR2(255) NOT NULL,
        full_name     VARCHAR2(100) NOT NULL,
        role          VARCHAR2(20) DEFAULT ''Faculty'' CHECK (role IN (''Administrator'', ''Faculty'')),
        email         VARCHAR2(100) NOT NULL UNIQUE,
        created_at    DATE DEFAULT SYSDATE
    )';
EXCEPTION WHEN OTHERS THEN NULL;
END;
/

BEGIN
    EXECUTE IMMEDIATE 'CREATE TABLE Proctor (
        proctor_id     VARCHAR2(15) PRIMARY KEY,
        proctor_name   VARCHAR2(60) NOT NULL,
        department     VARCHAR2(50),
        email          VARCHAR2(60) UNIQUE,
        phone          VARCHAR2(20),
        assigned_room  VARCHAR2(30)
    )';
EXCEPTION WHEN OTHERS THEN NULL;
END;
/

BEGIN
    EXECUTE IMMEDIATE 'CREATE TABLE Emergency_Contact (
        contact_id     NUMBER PRIMARY KEY,
        student_id     VARCHAR2(15) NOT NULL,
        contact_name   VARCHAR2(60) NOT NULL,
        relationship   VARCHAR2(30),
        phone_number   VARCHAR2(20) NOT NULL,
        email          VARCHAR2(60),
        CONSTRAINT fk_mig_contact_student FOREIGN KEY (student_id)
            REFERENCES Student(student_id) ON DELETE CASCADE
    )';
EXCEPTION WHEN OTHERS THEN NULL;
END;
/

BEGIN
    EXECUTE IMMEDIATE 'CREATE TABLE Camera_Nodes (
        node_id          VARCHAR2(20) PRIMARY KEY,
        device_id        NUMBER NOT NULL,
        ip_address       VARCHAR2(30),
        resolution       VARCHAR2(20) DEFAULT ''1080p'',
        frame_rate       NUMBER DEFAULT 30,
        firmware_version VARCHAR2(20) DEFAULT ''v2.4.1'',
        stream_status    VARCHAR2(20) DEFAULT ''Online'' CHECK (stream_status IN (''Online'', ''Degraded'', ''Offline'')),
        CONSTRAINT fk_mig_node_device FOREIGN KEY (device_id)
            REFERENCES Device(device_id) ON DELETE CASCADE
    )';
EXCEPTION WHEN OTHERS THEN NULL;
END;
/

BEGIN
    EXECUTE IMMEDIATE 'CREATE TABLE Alert_Notifications (
        notification_id NUMBER PRIMARY KEY,
        alert_id        NUMBER NOT NULL,
        recipient       VARCHAR2(100) NOT NULL,
        channel         VARCHAR2(10) CHECK (channel IN (''Email'', ''SMS'')),
        sent_time       DATE DEFAULT SYSDATE,
        status          VARCHAR2(15) DEFAULT ''Simulated'' CHECK (status IN (''Delivered'', ''Simulated'', ''Failed'')),
        message_text    VARCHAR2(300) NOT NULL,
        CONSTRAINT fk_mig_notif_alert FOREIGN KEY (alert_id) REFERENCES Alert(alert_id) ON DELETE CASCADE
    )';
EXCEPTION WHEN OTHERS THEN NULL;
END;
/

BEGIN
    EXECUTE IMMEDIATE 'CREATE TABLE Audit_Log (
        audit_id     NUMBER PRIMARY KEY,
        action_type  VARCHAR2(30) NOT NULL,
        table_name   VARCHAR2(30) NOT NULL,
        record_id    VARCHAR2(50) NOT NULL,
        performed_by VARCHAR2(50) NOT NULL,
        action_time  DATE DEFAULT SYSDATE,
        details      VARCHAR2(500)
    )';
EXCEPTION WHEN OTHERS THEN NULL;
END;
/

-- 6. Re-seed default admin & faculty users if table empty
DECLARE
    v_user_count NUMBER;
BEGIN
    SELECT COUNT(*) INTO v_user_count FROM Users;
    IF v_user_count = 0 THEN
        INSERT INTO Users VALUES (1, 'admin', 'pbkdf2:sha256:600000$tJ9P0v2x$58b3c1ec252f9547d698e4f553f18e998797e55ce91ad05d0e2e92cbb4d99411', 'Chief Invigilator (Admin)', 'Administrator', 'admin@example.com', SYSDATE);
        INSERT INTO Users VALUES (2, 'faculty', 'pbkdf2:sha256:600000$rT2W8v7x$49a1d2ec141f8436c587d3e442e07d887686d44bd80ac04c0d1d81baa3c88302', 'Faculty Demo', 'Faculty', 'faculty@example.com', SYSDATE);
        COMMIT;
    END IF;
END;
/

PROMPT Student monitoring schema migration completed successfully!
